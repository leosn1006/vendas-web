#!/usr/bin/env python3
"""
Corrige NF-e da LBE autorizadas pela SEFAZ com cStat=150 ("Autorizado o uso da
NF-e, autorizacao fora do prazo regulamentar") que o app classificou errado como
'rejeitada'.

Bug (corrigido em app/fiscal/nfe_service.py, commit desta sessão): as funções
_processar_retorno/_processar_retorno_cartao só tratavam cStat==100 como
autorização — qualquer outro valor, incluindo 150 (que também é autorização
válida, com protocolo real; o 150 só indica que a SEFAZ demorou além do SLA
normal pra responder, não um problema com os dados enviados), caía no branch de
rejeição e não gravava n_prot/dh_recbto/xml_nfe_proc.

Este script NÃO perde nada: os dados completos da resposta da SEFAZ (incluindo
nProt) já estão salvos em nfe_log_comunicacao.soap_response desde o envio
original. O script reparseia essa resposta com o MESMO parser de produção
(fiscal.nfe_soap._parsear_ret_envi_nfe) e remonta o nfeProc com a MESMA função
de produção (fiscal.nfe_service._montar_nfe_proc) — não reimplementa nada,
só reaplica a lógica que já roda pra cStat=100 com sucesso.

Escopo, de propósito: só mexe em linhas com status_emissao='rejeitada' E
c_stat='150' (a assinatura exata deste bug). Qualquer linha rejeitada por outro
motivo real (cStat >= 200) não é tocada.

Segurança: pra cada linha, reparseia o soap_response e CONFERE que o cStat
reparseado bate com o já gravado no banco antes de aplicar qualquer mudança —
se não bater (ou o log não existir/não tiver protNFe), a linha vai pra lista de
erros e não é gravada, sem afetar as demais.

Uso:
    python scripts/corrigir_nfe_fora_de_prazo_lbe.py --dry-run
    python scripts/corrigir_nfe_fora_de_prazo_lbe.py --aplicar
"""
import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv()

if os.getenv('DB_HOST') == 'db':
    os.environ['DB_HOST'] = 'localhost'

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from database import db  # noqa: E402
from fiscal.nfe_soap import _parsear_ret_envi_nfe  # noqa: E402
from fiscal.nfe_service import _montar_nfe_proc, _C_STAT_AUTORIZADOS  # noqa: E402

TENANT_ID_LBE = 2


def buscar_linhas_afetadas(cursor):
    cursor.execute(
        """SELECT id, numero, chave_acesso, c_stat, xml_assinado,
                  pagamento_pix_id, pagamento_cartao_id
           FROM nfe_emitidas
           WHERE tenant_id = %s AND status_emissao = 'rejeitada' AND c_stat = '150'""",
        (TENANT_ID_LBE,),
    )
    return cursor.fetchall()


def buscar_soap_response(cursor, nfe_id):
    cursor.execute(
        "SELECT soap_response FROM nfe_log_comunicacao WHERE nfe_id = %s ORDER BY id DESC LIMIT 1",
        (nfe_id,),
    )
    row = cursor.fetchone()
    return row['soap_response'] if row else None


def processar_linha(cursor, linha):
    """Retorna (erro_ou_None, dados_pra_gravar_ou_None)."""
    soap_response = buscar_soap_response(cursor, linha['id'])
    if not soap_response:
        return f'numero={linha["numero"]}: sem soap_response em nfe_log_comunicacao', None

    parsed = _parsear_ret_envi_nfe(soap_response)
    if parsed['prot_c_stat'] != linha['c_stat']:
        return (f'numero={linha["numero"]}: cStat reparseado ({parsed["prot_c_stat"]!r}) '
                f'diverge do gravado ({linha["c_stat"]!r})'), None
    if parsed['prot_c_stat'] not in _C_STAT_AUTORIZADOS:
        return f'numero={linha["numero"]}: cStat {parsed["prot_c_stat"]!r} não é autorização', None
    if not parsed['n_prot'] or not parsed['prot_nfe_xml']:
        return f'numero={linha["numero"]}: nProt ou protNFe ausente no log', None

    nfe_proc = _montar_nfe_proc(linha['xml_assinado'], parsed['prot_nfe_xml'])
    return None, {
        'nfe_id': linha['id'],
        'n_prot': parsed['n_prot'],
        'dh_recbto': parsed['dh_recbto'],
        'xml_nfe_proc': nfe_proc,
        'pagamento_pix_id': linha['pagamento_pix_id'],
    }


def aplicar(cursor, dados):
    cursor.execute(
        """UPDATE nfe_emitidas
           SET status_emissao = 'autorizada', n_prot = %s, dh_recbto = %s, xml_nfe_proc = %s
           WHERE id = %s""",
        (dados['n_prot'], dados['dh_recbto'], dados['xml_nfe_proc'], dados['nfe_id']),
    )
    if dados['pagamento_pix_id']:
        cursor.execute(
            "UPDATE pagamento_pix SET nfe_emitida_id = %s WHERE id = %s AND nfe_emitida_id IS NULL",
            (dados['nfe_id'], dados['pagamento_pix_id']),
        )


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    modo = ap.add_mutually_exclusive_group(required=True)
    modo.add_argument('--dry-run', action='store_true')
    modo.add_argument('--aplicar', action='store_true')
    args = ap.parse_args()

    erros = []
    prontos = []

    with db.get_cursor() as cursor:
        linhas = buscar_linhas_afetadas(cursor)
        print(f'[busca] {len(linhas)} linha(s) com status=rejeitada e c_stat=150')

        for linha in linhas:
            erro, dados = processar_linha(cursor, linha)
            if erro:
                erros.append(erro)
            else:
                prontos.append(dados)

        print(f'[validação] {len(prontos)} prontas pra corrigir | {len(erros)} erro(s)')
        if erros:
            print('\nLinhas com erro (não serão tocadas):')
            for e in erros:
                print(f'  - {e}')

        if not prontos:
            print('\nNada pra corrigir.')
            return

        if args.dry_run:
            print('\n[dry-run] Nenhuma escrita foi feita (rode com --aplicar pra gravar).')
            return

        for dados in prontos:
            aplicar(cursor, dados)

        print(f'\n[aplicado] {len(prontos)} nota(s) corrigida(s) pra autorizada, com protocolo e XML completos.')
        print('[aplicado] Transação será commitada ao sair do bloco (sem erros).')


if __name__ == '__main__':
    main()
