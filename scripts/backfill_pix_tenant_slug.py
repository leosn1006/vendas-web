"""
Back-fill de tenant_slug em pagamento_pix para registros de 2026-08-20 em diante.

Chama a API do BB para o tenant lbe-livros dia a dia e marca cada e2e_id
encontrado com tenant_slug = 'lbe-livros'. O restante (não encontrado na API LBE)
fica como NULL para ser tratado pela migration 070 final.

Execução (dentro do container ou com venv):
    python scripts/backfill_pix_tenant_slug.py

Após rodar com sucesso, executar no banco:
    UPDATE pagamento_pix SET tenant_slug = 'lsn-livros' WHERE tenant_slug IS NULL;
    ALTER TABLE pagamento_pix MODIFY COLUMN tenant_slug VARCHAR(50) NOT NULL DEFAULT 'lsn-livros';
"""

import sys
import os
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import database as db

TENANT = 'lbe-livros'
INICIO = date(2026, 8, 20)
FIM    = date.today()


def _marcar_lbe(e2e_id: str) -> None:
    db.db.execute_query(
        "UPDATE pagamento_pix SET tenant_slug = %s WHERE e2e_id = %s AND tenant_slug IS NULL",
        (TENANT, e2e_id),
    )


def main():
    from bb_pix import consultar_todos_pix
    from datetime import datetime as dt

    dia = INICIO
    total_marcados = 0
    while dia <= FIM:
        data_str = dia.strftime('%Y-%m-%d')
        print(f'[{data_str}] consultando API LBE...', end=' ', flush=True)
        try:
            inicio_dt = dt.strptime(f'{data_str}T00:00:00', '%Y-%m-%dT%H:%M:%S')
            fim_dt    = dt.strptime(f'{data_str}T23:59:59', '%Y-%m-%dT%H:%M:%S')
            pix_list  = consultar_todos_pix(inicio_dt, fim_dt, tenant_slug=TENANT)
            marcados = 0
            for pix in pix_list:
                e2e = pix.get('endToEndId') or ''
                if e2e:
                    _marcar_lbe(e2e)
                    marcados += 1
            total_marcados += marcados
            print(f'{len(pix_list)} PIX → {marcados} marcados')
        except Exception as exc:
            print(f'ERRO: {exc}')
        dia += timedelta(days=1)

    print(f'\nTotal marcado como lbe-livros: {total_marcados}')
    print('Agora execute no banco:')
    print("  UPDATE pagamento_pix SET tenant_slug = 'lsn-livros' WHERE tenant_slug IS NULL;")
    print("  ALTER TABLE pagamento_pix MODIFY COLUMN tenant_slug VARCHAR(50) NOT NULL DEFAULT 'lsn-livros';")


if __name__ == '__main__':
    main()
