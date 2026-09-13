#!/usr/bin/env python3
"""
Backfill de NF-e da LBE autorizadas de verdade na SEFAZ mas nunca persistidas no
banco de produção.

Contexto: o `nfe_configuracao.ambiente` da LBE no banco de DEV estava, por engano,
apontando pra produção real (=1) em vez de homologação (=2), com o certificado real
da empresa. Em 10/09/2026 a rotina `emitir_nfe_diaria_lbe` foi testada manualmente
duas vezes seguidas nesse ambiente de dev (via `make emitir-nfe-agora`), e as duas
rodadas — cada uma batendo no LIMIT de 500 — foram autorizadas de verdade pela SEFAZ
(1002 NF-e reais, números 6 a 1007, clientes reais da LBE). Isso nunca foi gravado no
banco de PRODUÇÃO, que só ficou sabendo da nota número 5 (teste manual anterior,
correto). Quando a rotina de produção rodou pela primeira vez em 12/09, tentou emitir
pros mesmos pagamentos e colidiu (cStat=539, duplicidade) porque a SEFAZ já tinha
essas notas.

Este script lê um export JSON do banco de DEV (fonte da verdade — tem os dados
completos: chave, protocolo, XML assinado e XML final com o protocolo da SEFAZ) e
reconcilia o banco de PRODUÇÃO:
  1. VALIDA cada linha contra o pagamento_pix/pagamento_cartao correspondente em
     produção (mesmo id, mesmo CPF/CNPJ, mesmo valor). Se qualquer linha não bater,
     o script para SEM gravar nada — correção fiscal não admite "gravar a maioria e
     revisar o resto depois".
  2. Só se 100% das linhas validarem: persiste. Pra pagamento que já tem uma linha em
     nfe_emitidas (os 503 que a produção tentou em 12/09 e ficaram 'rejeitada') faz
     UPDATE; pra pagamento que nunca foi tentado em produção, faz INSERT. Em seguida
     vincula pagamento_pix.nfe_emitida_id (cartão não precisa — o vínculo é só via
     nfe_emitidas.pagamento_cartao_id).
  3. Idempotente: se uma linha já está com status_emissao='autorizada' E a mesma
     chave_acesso do export, é pulada (script pode rodar de novo sem duplicar nem
     reescrever à toa). Se já está 'autorizada' com uma chave DIFERENTE da do export,
     isso é tratado como erro — sinal de conflito real que precisa de revisão manual,
     nunca sobrescrito silenciosamente.
  4. Tudo dentro de uma única transação: se qualquer escrita falhar no meio, dá
     rollback completo, não fica pela metade.

Nunca mexe em nfe_configuracao.ultimo_numero_nfe nem religa a rotina — isso é um
passo manual separado, só depois de conferir a saída deste script.

Uso:
    python scripts/backfill_nfe_lbe_producao.py --arquivo nfe_lbe_export.json --dry-run
    python scripts/backfill_nfe_lbe_producao.py --arquivo nfe_lbe_export.json --aplicar
"""
import argparse
import decimal
import json
import os
import re
import sys

from dotenv import load_dotenv

load_dotenv()

# Este script roda no host (fora da rede Docker): DB_HOST='db' não resolve aqui.
if os.getenv('DB_HOST') == 'db':
    os.environ['DB_HOST'] = 'localhost'

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from database import db  # noqa: E402

TENANT_ID_LBE = 2


def normalizar_doc(valor):
    if valor is None:
        return None
    return re.sub(r'\D', '', str(valor))


def normalizar_valor(valor):
    if valor is None:
        return None
    return decimal.Decimal(str(valor)).quantize(decimal.Decimal('0.01'))


def carregar_export(caminho):
    with open(caminho, encoding='utf-8') as f:
        linhas = json.load(f)
    print(f'[export] {len(linhas)} linhas carregadas de {caminho}')
    return linhas


def buscar_pagamento_pix(cursor, pix_id):
    cursor.execute(
        """SELECT id, cpf_cnpj, valor, nome_pagador, nfe_emitida_id
           FROM pagamento_pix WHERE id = %s""",
        (pix_id,),
    )
    return cursor.fetchone()


def buscar_pagamento_cartao(cursor, cartao_id):
    cursor.execute(
        """SELECT pc.id, pc.valor, ped.cpf_cnpj_pagador AS cpf_cnpj, ped.nome_pagador
           FROM pagamento_cartao pc
           JOIN pedidos ped ON ped.id = pc.pedido_id
           WHERE pc.id = %s""",
        (cartao_id,),
    )
    return cursor.fetchone()


def buscar_nfe_existente(cursor, pix_id, cartao_id):
    if pix_id:
        cursor.execute(
            "SELECT id, chave_acesso, status_emissao FROM nfe_emitidas WHERE pagamento_pix_id = %s",
            (pix_id,),
        )
    else:
        cursor.execute(
            "SELECT id, chave_acesso, status_emissao FROM nfe_emitidas WHERE pagamento_cartao_id = %s",
            (cartao_id,),
        )
    return cursor.fetchone()


def validar_linha(cursor, linha):
    """Retorna (erro_ou_None, acao, nfe_existente_ou_None)."""
    pix_id = linha['pagamento_pix_id']
    cartao_id = linha['pagamento_cartao_id']

    if pix_id:
        pagamento = buscar_pagamento_pix(cursor, pix_id)
        if not pagamento:
            return f'pagamento_pix_id={pix_id} (numero={linha["numero"]}) não existe em produção', None, None
        doc_prod, doc_dev = normalizar_doc(pagamento['cpf_cnpj']), normalizar_doc(linha['pix_cpf_cnpj'])
        valor_prod, valor_dev = normalizar_valor(pagamento['valor']), normalizar_valor(linha['pix_valor'])
    elif cartao_id:
        pagamento = buscar_pagamento_cartao(cursor, cartao_id)
        if not pagamento:
            return f'pagamento_cartao_id={cartao_id} (numero={linha["numero"]}) não existe em produção', None, None
        doc_prod, doc_dev = normalizar_doc(pagamento['cpf_cnpj']), normalizar_doc(linha['cartao_cpf_cnpj'])
        valor_prod, valor_dev = normalizar_valor(pagamento['valor']), normalizar_valor(linha['cartao_valor'])
    else:
        return f'numero={linha["numero"]}: sem pagamento_pix_id nem pagamento_cartao_id no export', None, None

    if doc_prod != doc_dev:
        return (f'numero={linha["numero"]}: CPF/CNPJ diverge '
                f'(produção={doc_prod!r} dev={doc_dev!r})'), None, None
    if valor_prod != valor_dev:
        return (f'numero={linha["numero"]}: valor diverge '
                f'(produção={valor_prod} dev={valor_dev})'), None, None

    nfe_existente = buscar_nfe_existente(cursor, pix_id, cartao_id)
    if nfe_existente is None:
        return None, 'inserir', None
    if nfe_existente['chave_acesso'] == linha['chave_acesso'] and nfe_existente['status_emissao'] == 'autorizada':
        return None, 'pular', nfe_existente
    if nfe_existente['status_emissao'] == 'autorizada' and nfe_existente['chave_acesso'] != linha['chave_acesso']:
        return (f'numero={linha["numero"]}: já existe NF-e AUTORIZADA em produção com chave '
                f'DIFERENTE da do dev (produção={nfe_existente["chave_acesso"]} '
                f'dev={linha["chave_acesso"]}) — conflito real, requer revisão manual'), None, None
    return None, 'atualizar', nfe_existente


def aplicar_insercao(cursor, linha):
    cursor.execute(
        """INSERT INTO nfe_emitidas
               (tenant_id, pagamento_pix_id, pagamento_cartao_id, chave_acesso, numero, serie,
                ambiente, c_stat, status_emissao, n_prot, dh_recbto, xml_assinado, xml_nfe_proc,
                tentativas)
           VALUES (%s, %s, %s, %s, %s, %s, 1, %s, 'autorizada', %s, %s, %s, %s, 1)""",
        (
            TENANT_ID_LBE, linha['pagamento_pix_id'], linha['pagamento_cartao_id'],
            linha['chave_acesso'], linha['numero'], linha['serie'], linha['c_stat'],
            linha['n_prot'], linha['dh_recbto'], linha['xml_assinado'], linha['xml_nfe_proc'],
        ),
    )
    return cursor.lastrowid


def aplicar_atualizacao(cursor, linha, nfe_id):
    cursor.execute(
        """UPDATE nfe_emitidas
           SET chave_acesso = %s, status_emissao = 'autorizada', c_stat = %s,
               n_prot = %s, dh_recbto = %s, xml_assinado = %s, xml_nfe_proc = %s
           WHERE id = %s""",
        (
            linha['chave_acesso'], linha['c_stat'], linha['n_prot'], linha['dh_recbto'],
            linha['xml_assinado'], linha['xml_nfe_proc'], nfe_id,
        ),
    )


def vincular_pix(cursor, pix_id, nfe_id):
    cursor.execute(
        "UPDATE pagamento_pix SET nfe_emitida_id = %s WHERE id = %s AND nfe_emitida_id IS NULL",
        (nfe_id, pix_id),
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--arquivo', required=True, help='Caminho do export JSON gerado no dev')
    modo = ap.add_mutually_exclusive_group(required=True)
    modo.add_argument('--dry-run', action='store_true', help='Só valida e reporta, não grava nada')
    modo.add_argument('--aplicar', action='store_true', help='Valida e, se tudo OK, grava de verdade')
    args = ap.parse_args()

    linhas = carregar_export(args.arquivo)

    erros = []
    plano = {'inserir': [], 'atualizar': [], 'pular': []}

    with db.get_cursor() as cursor:
        for linha in linhas:
            erro, acao, nfe_existente = validar_linha(cursor, linha)
            if erro:
                erros.append(erro)
                continue
            plano[acao].append((linha, nfe_existente))

        print(f'\n[validação] {len(linhas)} linhas | '
              f'{len(plano["inserir"])} pra inserir | '
              f'{len(plano["atualizar"])} pra atualizar | '
              f'{len(plano["pular"])} já corretas (pulo) | '
              f'{len(erros)} erro(s)')

        if erros:
            print('\n[ABORTADO] Erros encontrados — nada foi gravado:')
            for e in erros:
                print(f'  - {e}')
            sys.exit(1)

        if args.dry_run:
            print('\n[dry-run] Validação OK. Nenhuma escrita foi feita (rode com --aplicar pra gravar).')
            return

        inseridos = 0
        atualizados = 0
        pix_vinculados = 0

        for linha, _ in plano['inserir']:
            nfe_id = aplicar_insercao(cursor, linha)
            inseridos += 1
            if linha['pagamento_pix_id']:
                vincular_pix(cursor, linha['pagamento_pix_id'], nfe_id)
                pix_vinculados += 1

        for linha, nfe_existente in plano['atualizar']:
            aplicar_atualizacao(cursor, linha, nfe_existente['id'])
            atualizados += 1
            if linha['pagamento_pix_id']:
                vincular_pix(cursor, linha['pagamento_pix_id'], nfe_existente['id'])
                pix_vinculados += 1

        print(f'\n[aplicado] {inseridos} inserida(s), {atualizados} atualizada(s), '
              f'{len(plano["pular"])} já estavam corretas, {pix_vinculados} pagamento_pix vinculado(s).')
        print('[aplicado] Transação será commitada ao sair do bloco (sem erros).')


if __name__ == '__main__':
    main()
