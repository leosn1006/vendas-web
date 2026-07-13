"""
Testes de integração NF-e — requerem banco de dados acessível e certificado A1.

Excluídos da suite padrão (`pytest`) para não exigir banco em CI.
Rodar localmente antes de habilitar a NF-e em produção.

Camada 1 — configuração do banco (leitura):
    python -m pytest tests/fiscal/test_nfe_integracao.py -v

Camada 2 — pipeline com dados reais (sem envio para SEFAZ):
    NF_CERT_SENHA="..." python -m pytest tests/fiscal/test_nfe_integracao.py -v

Camada 3 — envio real para SEFAZ homologação:
    NF_CERT_SENHA="..." python -m pytest tests/fiscal/test_nfe_integracao.py -v -m sefaz
"""
import os
import sys
import pytest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'app'))

pytestmark = pytest.mark.integration


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _carregar_config():
    try:
        from database import buscar_nfe_configuracao_ativa
        config = buscar_nfe_configuracao_ativa()
    except Exception as e:
        pytest.skip(f'Banco indisponível: {e}')
    if not config:
        pytest.skip('Nenhuma nfe_configuracao ativa no banco')
    return config


def _carregar_pix_recente():
    try:
        from database import db
        pix = db.execute_query(
            """SELECT id, cpf_cnpj, nome_pagador, valor
               FROM pagamento_pix
               WHERE cpf_cnpj IS NOT NULL AND cpf_cnpj != ''
               ORDER BY horario DESC LIMIT 1""",
            fetch_one=True,
        )
    except Exception as e:
        pytest.skip(f'Banco indisponível ao buscar PIX: {e}')
    if not pix:
        pytest.skip('Nenhum pagamento_pix com CPF/CNPJ encontrado no banco')
    return pix


def _senha(config) -> str:
    env_var = config.get('certificado_senha_env', '')
    senha = os.getenv(env_var, '') if env_var else ''
    if not senha:
        pytest.skip(f'Variável {env_var!r} não definida — execute: export {env_var}="sua_senha"')
    return senha


# ─── Camada 1: configuração do banco ─────────────────────────────────────────

def test_config_cnpj_preenchido():
    config = _carregar_config()
    assert config.get('cnpj'), 'cnpj vazio em nfe_configuracao'


def test_config_ie_nao_isento():
    config = _carregar_config()
    ie = (config.get('ie') or '').strip().upper()
    assert ie and ie != 'ISENTO', (
        f'IE ainda como "{ie}" — preencher com IE real do SEFAZ-DF antes de ativar'
    )


def test_config_ncm_preenchido():
    config = _carregar_config()
    ncm = config.get('ncm') or ''
    assert len(ncm) == 8, f'NCM inválido: "{ncm}" (deve ter 8 dígitos)'


def test_config_cfop_preenchido():
    config = _carregar_config()
    cfop = config.get('cfop') or ''
    assert len(cfop) == 4, f'CFOP inválido: "{cfop}" (deve ter 4 dígitos)'


def test_config_certificado_existe():
    config = _carregar_config()
    path = config.get('certificado_path', '')
    assert path, 'certificado_path vazio em nfe_configuracao'
    assert os.path.exists(path), f'Arquivo de certificado não encontrado: {path}'


def test_config_senha_env_definida():
    config = _carregar_config()
    _senha(config)  # pula se a env var não estiver definida


# ─── Camada 2: pipeline com dados reais (sem envio para SEFAZ) ───────────────

def test_pipeline_monta_e_valida_xml():
    """Lê config + PIX real do banco, roda gerar_chave → montar → assinar → XSD."""
    config = _carregar_config()
    pix    = _carregar_pix_recente()
    senha  = _senha(config)

    from fiscal.certificado import carregar_pfx
    from fiscal.nfe_chave import gerar_chave
    from fiscal.nfe_xml_builder import montar_nfe
    from fiscal.nfe_assinador import assinar_nfe
    from fiscal.nfe_validador import validar_nfe

    cert_pem, key_pem, _ = carregar_pfx(config['certificado_path'], senha)
    data = datetime.now()
    chave44, c_nf = gerar_chave('53', data, config['cnpj'], '55', config.get('serie_padrao', '001'), 1)

    xml = montar_nfe(config, pix, 1, chave44, c_nf, data)
    xml_assinado = assinar_nfe(xml, key_pem, cert_pem)

    erros = validar_nfe(xml_assinado)
    assert not erros, f'XML inválido contra XSD com dados reais: {erros}'


def test_pipeline_gera_danfe():
    """Verifica que o XML com dados reais gera um PDF DANFE sem erros."""
    config = _carregar_config()
    pix    = _carregar_pix_recente()
    senha  = _senha(config)

    from fiscal.certificado import carregar_pfx
    from fiscal.nfe_chave import gerar_chave
    from fiscal.nfe_xml_builder import montar_nfe
    from fiscal.nfe_assinador import assinar_nfe
    from brazilfiscalreport.danfe import Danfe

    cert_pem, key_pem, _ = carregar_pfx(config['certificado_path'], senha)
    data = datetime.now()
    chave44, c_nf = gerar_chave('53', data, config['cnpj'], '55', config.get('serie_padrao', '001'), 1)
    xml = montar_nfe(config, pix, 1, chave44, c_nf, data)
    xml_assinado = assinar_nfe(xml, key_pem, cert_pem)

    danfe = Danfe(xml=xml_assinado)
    pdf_bytes = danfe.output()
    assert len(pdf_bytes) > 1000, 'PDF gerado parece vazio'


# ─── Camada 3: envio real para SEFAZ homologação ─────────────────────────────

@pytest.mark.sefaz
def test_envio_homologacao_retorna_http_200():
    """
    Envia NF-e para SVRS homologação e confirma que a comunicação funciona.
    Não grava no banco — só testa o pipeline de comunicação.
    cStat esperado: 104/209 (209 = IE inválida, esperado até IE chegar do SEFAZ-DF).
    """
    config = _carregar_config()
    pix    = _carregar_pix_recente()
    senha  = _senha(config)

    from fiscal.certificado import carregar_pfx, certificado_temp
    from fiscal.nfe_chave import gerar_chave
    from fiscal.nfe_xml_builder import montar_nfe
    from fiscal.nfe_assinador import assinar_nfe
    from fiscal.nfe_validador import validar_nfe
    from fiscal.nfe_soap import enviar_autorizacao

    cert_pem, key_pem, _ = carregar_pfx(config['certificado_path'], senha)
    data = datetime.now()
    chave44, c_nf = gerar_chave('53', data, config['cnpj'], '55', config.get('serie_padrao', '001'), 1)

    # Força homologação mesmo que o config aponte para produção
    config_hml = {**config, 'ambiente': 2}
    xml = montar_nfe(config_hml, pix, 1, chave44, c_nf, data)
    xml_assinado = assinar_nfe(xml, key_pem, cert_pem)

    erros = validar_nfe(xml_assinado)
    assert not erros, f'XSD falhou antes de enviar: {erros}'

    with certificado_temp(config['certificado_path'], senha) as (cert_path, key_path, _):
        resultado = enviar_autorizacao(
            xml_nfe_assinado=xml_assinado,
            cert_path=cert_path,
            key_path=key_path,
            ambiente=2,
            verify=False,
        )

    assert resultado['status_http'] == 200, f'HTTP inesperado: {resultado["status_http"]}'
    assert resultado['c_stat'], 'cStat ausente no retorno SEFAZ'

    print(f"\n  cStat={resultado['c_stat']} — {resultado['x_motivo']}")
    if resultado['prot_c_stat']:
        print(f"  protCStat={resultado['prot_c_stat']} — {resultado['prot_x_motivo']}")
