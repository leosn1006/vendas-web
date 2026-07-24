"""
Testa (somente leitura) como a API Pix do BB retorna uma devolucao e como ela se
relaciona com o Pix original.

Nao envia nenhuma escrita na API — apenas GET (consultar_todos_pix + uma
consulta extra com o filtro devolucaoPresente=true).

O que o script faz:
  1. Consulta GET /pix do periodo informado (padrao: hoje) e procura o Pix de
     valor 341.00, mostrando se o campo `devolucoes` aparece aninhado dentro
     dele (e nao como uma transacao separada).
  2. Repete a mesma consulta com o filtro `devolucaoPresente=true`, para
     confirmar que a API permite filtrar direto os Pix que tem devolucao
     associada dentro do periodo pesquisado.

Uso:
  python scripts/testar_devolucao_pix.py
  python scripts/testar_devolucao_pix.py --data 2026-07-23
  python scripts/testar_devolucao_pix.py --data 2026-07-23 --valor 341.00
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _AQUI)
sys.path.insert(0, os.path.join(_AQUI, '..'))
load_dotenv()

try:
    from app import bb_pix  # execução local, fora do container (repo root)
except ImportError:
    import bb_pix  # execução dentro do container (WORKDIR /app == app/ do repo)

TZ_BR = timezone(timedelta(hours=-3))


def consultar_com_filtro(inicio: datetime, fim: datetime, devolucao_presente: bool) -> list:
    """Mesma paginacao de bb_pix.consultar_todos_pix, com o filtro devolucaoPresente."""
    token = bb_pix._get_token()
    todos = []
    pagina = 0

    while True:
        resp = requests.get(
            f'{bb_pix._API_URL}/pix',
            params={
                'inicio': inicio.isoformat(),
                'fim': fim.isoformat(),
                'devolucaoPresente': str(devolucao_presente).lower(),
                'gw-dev-app-key': bb_pix._APP_KEY,
                'paginacao.paginaAtual': pagina,
                'paginacao.itensPorPagina': 100,
            },
            headers={'Authorization': f'Bearer {token}'},
            cert=(bb_pix._CERT_PEM, bb_pix._CERT_KEY),
            timeout=15,
        )
        if resp.status_code == 404:
            break
        resp.raise_for_status()

        data = resp.json()
        paginacao = data.get('parametros', {}).get('paginacao', {})
        todos.extend(data.get('pix', []))

        if paginacao.get('paginaAtual', pagina) >= paginacao.get('quantidadeDePaginas', 1) - 1:
            break
        pagina += 1

    return todos


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', help='Data (YYYY-MM-DD) final da janela. Padrao: hoje.')
    parser.add_argument('--valor', default='341.88', help='Valor do Pix a localizar (padrao: 341.88).')
    parser.add_argument('--dias', type=int, default=0,
                         help='Quantos dias voltar a partir de --data/hoje (janela retroativa). Padrao: 0 (so o dia).')
    args = parser.parse_args()

    if args.data:
        fim_dia = datetime.strptime(args.data, '%Y-%m-%d').replace(tzinfo=TZ_BR)
        fim = fim_dia.replace(hour=23, minute=59, second=59, microsecond=0)
    else:
        fim = datetime.now(TZ_BR)

    inicio = (fim - timedelta(days=args.dias)).replace(hour=0, minute=0, second=0, microsecond=0)

    print(f'Periodo consultado: {inicio.isoformat()} ate {fim.isoformat()}\n')

    # 1) Consulta normal (sem filtro) — igual ao fluxo ja usado em producao
    print('=== 1) GET /pix (sem filtro) ===')
    todos = bb_pix.consultar_todos_pix(inicio, fim)
    print(f'Total de Pix recebidos no periodo: {len(todos)}\n')

    encontrado = None
    for p in todos:
        if p.get('valor') == args.valor:
            encontrado = p
            break

    if encontrado:
        print(f'>>> Encontrado Pix de valor {args.valor}:')
        print(json.dumps(encontrado, indent=2, ensure_ascii=False))
        if 'devolucoes' in encontrado:
            print('\n>>> CONFIRMADO: campo "devolucoes" presente DENTRO do Pix original.')
            for d in encontrado['devolucoes']:
                print(f"    id={d.get('id')} rtrId={d.get('rtrId')} valor={d.get('valor')} "
                      f"status={d.get('status')} horario={d.get('horario')}")
        else:
            print('\n>>> Pix encontrado, mas SEM campo "devolucoes" (a API ainda nao registrou a devolucao aqui).')
    else:
        print(f'>>> Nenhum Pix de valor {args.valor} encontrado no periodo consultado.')
        print('    (pode ser que o Pix original tenha sido recebido em outro dia — use --data)')

    # 2) Consulta com o filtro devolucaoPresente=true, para confirmar que a API
    #    permite localizar direto os Pix do periodo que tem devolucao associada.
    print('\n=== 2) GET /pix?devolucaoPresente=true ===')
    try:
        com_devolucao = consultar_com_filtro(inicio, fim, devolucao_presente=True)
        print(f'Total de Pix com devolucao associada no periodo: {len(com_devolucao)}')
        for p in com_devolucao:
            print(json.dumps(p, indent=2, ensure_ascii=False))
            print(f"  >>> txid presente: {bool(p.get('txid'))}  (txid={p.get('txid')!r})")
    except requests.HTTPError as e:
        print(f'ERRO ao consultar com filtro devolucaoPresente=true: {e}')


if __name__ == '__main__':
    main()
