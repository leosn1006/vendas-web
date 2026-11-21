"""Valor da conversão no Google Ads: venda do site manda o valor real pago; WhatsApp, R$ 10 fixo."""
import sys
import types
from types import SimpleNamespace

# O fluxo importa a biblioteca do Google Ads no topo; sem ela instalada, um módulo falso basta para
# testar só a regra do valor (com ela instalada, usa a real e não interfere em outros testes).
try:
    import google.ads.googleads.client  # noqa: F401
except ImportError:
    for nome in ('google.ads', 'google.ads.googleads', 'google.ads.googleads.client'):
        sys.modules.setdefault(nome, types.ModuleType(nome))
    sys.modules['google.ads.googleads.client'].GoogleAdsClient = object

from datetime import datetime  # noqa: E402

import pytz  # noqa: E402

from fluxos import fluxo_upload_google_ads as fluxo  # noqa: E402
from fluxos.fluxo_upload_google_ads import _linhas_antigas, valor_conversao  # noqa: E402


def v(estado_id, valor_pago, produto_id=12):
    return SimpleNamespace(produto_id=produto_id, estado_id=estado_id, valor_pago=valor_pago)


def test_venda_do_site_manda_o_valor_real_pago():
    assert valor_conversao(v(1000, 22.0)) == '22.00'      # Completo
    assert valor_conversao(v(1000, '28.90')) == '28.90'   # plano + um bump
    assert valor_conversao(v(1000, 10.0)) == '10.00'      # Básico (antes: 20 fixo no produto 12)
    assert valor_conversao(v(1000, 6.9, produto_id=14)) == '6.90'


def test_venda_do_whatsapp_manda_10_fixo():
    # O comprovante do WhatsApp não é validado: o valor digitado pode não ser o pago.
    assert valor_conversao(v(0, 16.9)) == '10.00'
    assert valor_conversao(v(0, 10.0, produto_id=8)) == '10.00'


def test_venda_sem_valor_pago_cai_no_fixo():
    assert valor_conversao(v(1000, None)) == '10.00'
    assert valor_conversao(v(1000, 0)) == '10.00'
    assert valor_conversao(v(1000, 'lixo')) == '10.00'
    assert valor_conversao(SimpleNamespace(produto_id=12, valor_pago=22)) == '10.00'  # sem estado


# ── Limpeza da planilha: só os últimos 60 dias ────────────────────────────────

LIMITE = datetime(2026, 9, 22, 12, 0, 0)  # 60 dias antes de 21/11 às 12h


def _h(data):
    return f'{data} America/Sao_Paulo'


def test_linhas_recentes_ficam_e_antigas_saem():
    valores = ['Conversion Time', _h('2026-08-01 10:00:00'), _h('2026-08-02 10:00:00'), _h('2026-11-20 10:00:00')]
    assert _linhas_antigas(valores, LIMITE) == [(2, 3)]


def test_fora_de_ordem_vira_varios_trechos_do_fim_para_o_comeco():
    valores = ['Conversion Time', _h('2026-08-01 10:00:00'), _h('2026-11-01 10:00:00'), _h('2026-07-01 10:00:00'),
               _h('2026-07-02 10:00:00'), _h('2026-11-02 10:00:00'), _h('2026-06-01 10:00:00')]
    assert _linhas_antigas(valores, LIMITE) == [(7, 7), (4, 5), (2, 2)]


def test_cabecalho_vazia_e_ilegivel_ficam():
    valores = ['2020-01-01 00:00:00', '', 'qualquer coisa', None, _h('2026-08-01 10:00:00')]
    assert _linhas_antigas(valores, LIMITE) == [(5, 5)]


def test_so_a_data_tambem_vale():
    assert _linhas_antigas(['Conversion Time', '2026-08-01', '2026-11-01'], LIMITE) == [(2, 2)]


def test_linha_com_exatamente_60_dias_fica():
    assert _linhas_antigas(['Conversion Time', _h('2026-09-22 12:00:00'), _h('2026-09-22 11:59:59')], LIMITE) == [(3, 3)]


class _Aba:
    def __init__(self, coluna_c, falha=None):
        self.coluna_c, self.falha, self.id = coluna_c, falha, 42
        self.pedidos, self.acrescentadas, self.ordem = [], [], []
        self.spreadsheet = SimpleNamespace(batch_update=self._batch)

    def _batch(self, corpo):
        if self.falha:
            raise self.falha
        self.ordem.append('limpeza')
        self.pedidos.extend(corpo['requests'])

    def row_values(self, _):
        return ['Google Click ID']

    def col_values(self, coluna):
        assert coluna == 3
        return self.coluna_c

    def append_rows(self, linhas, value_input_option=None):
        self.ordem.append('acrescentar')
        self.acrescentadas.extend(linhas)


def _exportar(monkeypatch, aba):
    venda = dict(id=7, produto_id=1, estado_id=1000, valor_pago=47.9, gclid='G1', wbraid='', gbraid='',
                 data_pagamento=datetime(2026, 11, 20, 10, 0, 0), google_sheets_spreadsheet_id='PLAN',
                 google_sheets_sheet_name='Aba', google_ads_conversion_name='compra', google_sa_env_var='SA_TESTE')
    marcadas = []
    monkeypatch.setenv('SA_TESTE', '{}')
    monkeypatch.setattr(fluxo, 'busca_vendas_pendentes_google_por_dns', lambda: [venda])
    monkeypatch.setattr(fluxo, 'marcar_venda_como_enviada_ao_google_ads', marcadas.append)
    monkeypatch.setattr(fluxo.Credentials, 'from_service_account_info', lambda *a, **k: None)
    planilha = SimpleNamespace(worksheet=lambda nome: aba)
    monkeypatch.setattr(fluxo.gspread, 'authorize', lambda c: SimpleNamespace(open_by_key=lambda i: planilha))

    class _Agora(datetime):
        @classmethod
        def now(cls, tz=None):
            return pytz.timezone('America/Sao_Paulo').localize(datetime(2026, 11, 21, 12, 0, 0))
    monkeypatch.setattr(fluxo, 'datetime', _Agora)
    fluxo.exportar_para_google_sheets()
    return marcadas


def test_acrescenta_e_depois_apaga_as_antigas_numa_chamada(monkeypatch):
    aba = _Aba(['Conversion Time', _h('2026-08-01 10:00:00'), _h('2026-11-01 10:00:00'), _h('2026-07-01 10:00:00')])
    marcadas = _exportar(monkeypatch, aba)
    assert aba.ordem == ['acrescentar', 'limpeza']
    assert [p['deleteDimension']['range'] for p in aba.pedidos] == [
        {'sheetId': 42, 'dimension': 'ROWS', 'startIndex': 3, 'endIndex': 4},
        {'sheetId': 42, 'dimension': 'ROWS', 'startIndex': 1, 'endIndex': 2},
    ]
    assert aba.acrescentadas[0][0] == 'G1' and marcadas == [7]


def test_sem_linha_antiga_nao_chama_a_limpeza(monkeypatch):
    aba = _Aba(['Conversion Time', _h('2026-11-01 10:00:00')])
    _exportar(monkeypatch, aba)
    assert aba.ordem == ['acrescentar']


def test_erro_na_limpeza_ainda_envia_e_marca(monkeypatch):
    aba = _Aba(['Conversion Time', _h('2026-08-01 10:00:00')], falha=RuntimeError('cota'))
    marcadas = _exportar(monkeypatch, aba)
    assert aba.acrescentadas and marcadas == [7]


def test_ilegivel_fica_e_avisa(monkeypatch, caplog):
    aba = _Aba(['Conversion Time', '01/08/2026', _h('2026-11-01 10:00:00')])
    _exportar(monkeypatch, aba)
    assert aba.pedidos == [] and '1 linhas com Conversion Time ilegível' in caplog.text
