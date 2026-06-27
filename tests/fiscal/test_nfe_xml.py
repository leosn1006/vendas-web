"""
Testes para montagem e validação do XML da NF-e 4.00.

Cenário central: você muda um campo no nfe_xml_builder.py (adiciona, remove,
renomeia) → test_xml_valido_xsd falha imediatamente, antes de chegar à SEFAZ.

Os demais testes cobrem bugs específicos que encontramos durante o
desenvolvimento e que causaram rejeições silenciosas da SEFAZ:
  - indIntermed ausente → cStat=434
  - serie com zeros → cStat=215 (XSD)
  - xNome errado em homologação → cStat=598

Nota: o XSD da NF-e 4.00 requer <Signature> — a validação XSD é feita
sobre o XML já assinado, igual ao fluxo de produção. Os testes de assinatura
usam o fixture test_cert_pem_key_pem (certificado auto-assinado gerado em memória).
"""
from datetime import datetime

import pytest
from lxml import etree

from app.fiscal.nfe_chave import gerar_chave
from app.fiscal.nfe_xml_builder import montar_nfe
from app.fiscal.nfe_assinador import assinar_nfe
from app.fiscal.nfe_validador import validar_nfe

# ─── Fixtures ────────────────────────────────────────────────────────────────

_DT = datetime(2026, 6, 23, 10, 0, 0)
_CHAVE44, _C_NF = gerar_chave('53', _DT, '64980953000146', '55', '001', 999)

_CONFIG_HOMOLOGACAO = {
    'serie_padrao': '001',
    'ambiente': 2,
    'x_prod': 'Livro Digital de Teste',
    'ncm': '49011000',
    'cfop': '6107',
    'ie': None,
}

_CONFIG_PRODUCAO = {**_CONFIG_HOMOLOGACAO, 'ambiente': 1}

_PAGAMENTO = {
    'cpf_cnpj': '12345678909',
    'nome_pagador': 'JOAO DA SILVA',
    'valor': '97.00',
}

_PAGAMENTO_SEM_CPF = {
    'cpf_cnpj': None,
    'nome_pagador': 'ANONIMO',
    'valor': '47.00',
}


def _montar(config=None, pagamento=None):
    return montar_nfe(
        config   or _CONFIG_HOMOLOGACAO,
        pagamento or _PAGAMENTO,
        999, _CHAVE44, _C_NF, _DT,
    )


def _assinar(xml_str: str, cert_pem: bytes, key_pem: bytes) -> bytes:
    return assinar_nfe(xml_str, key_pem, cert_pem)


# ─── Validade XSD ────────────────────────────────────────────────────────────
# O XSD da NF-e 4.00 exige <Signature>. Os testes assinam com certificado
# auto-assinado de teste — igual ao fluxo de produção, sem chamar a SEFAZ.

def test_xml_valido_xsd(test_cert_pem_key_pem):
    """Teste principal: qualquer campo adicionado/removido deve passar pelo XSD."""
    cert_pem, key_pem = test_cert_pem_key_pem
    xml = _montar()
    xml_assinado = _assinar(xml, cert_pem, key_pem)
    erros = validar_nfe(xml_assinado)
    assert erros == [], f'Erros XSD: {erros}'


def test_xml_producao_valido_xsd(test_cert_pem_key_pem):
    cert_pem, key_pem = test_cert_pem_key_pem
    xml = _montar(config=_CONFIG_PRODUCAO)
    xml_assinado = _assinar(xml, cert_pem, key_pem)
    erros = validar_nfe(xml_assinado)
    assert erros == [], f'Erros XSD em produção: {erros}'


# ─── Campos obrigatórios e anti-regressão ────────────────────────────────────

def test_ind_intermed_presente():
    """
    cStat=434 quando indIntermed ausente para indPres=2 (NT 2020.006).
    Se esse campo sumir do builder, a SEFAZ rejeita sem explicação clara.
    """
    xml = _montar()
    NS = 'http://www.portalfiscal.inf.br/nfe'
    root = etree.fromstring(xml.encode('utf-8'))
    ind = root.find(f'.//{{{NS}}}indIntermed')
    assert ind is not None, 'indIntermed está ausente no XML'
    assert ind.text == '0'


def test_serie_sem_zeros_no_xml():
    """
    XSD rejeita série '001' (pattern: 0|[1-9][0-9]{0,2}).
    O builder deve converter '001' → '1' no elemento XML.
    A chave de acesso usa zfill(3) separadamente.
    """
    xml = _montar()
    NS = 'http://www.portalfiscal.inf.br/nfe'
    root = etree.fromstring(xml.encode('utf-8'))
    serie_el = root.find(f'.//{{{NS}}}serie')
    assert serie_el is not None
    assert not serie_el.text.startswith('0') or serie_el.text == '0', (
        f"serie='{serie_el.text}' tem zero à esquerda — o XSD vai rejeitar"
    )


def test_xnome_homologacao_exato():
    """
    SVRS retorna cStat=598 se xNome do destinatário em homologação
    não for exatamente 'NF-E EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL'.
    """
    xml = _montar(config=_CONFIG_HOMOLOGACAO)
    NS = 'http://www.portalfiscal.inf.br/nfe'
    root = etree.fromstring(xml.encode('utf-8'))
    dest = root.find(f'.//{{{NS}}}dest')
    xnome = dest.find(f'{{{NS}}}xNome').text
    assert xnome == 'NF-E EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL'


def test_xnome_producao_usa_nome_pagador():
    xml = _montar(config=_CONFIG_PRODUCAO, pagamento=_PAGAMENTO)
    NS = 'http://www.portalfiscal.inf.br/nfe'
    root = etree.fromstring(xml.encode('utf-8'))
    dest = root.find(f'.//{{{NS}}}dest')
    xnome = dest.find(f'{{{NS}}}xNome').text
    assert xnome == 'JOAO DA SILVA'


def test_id_attribute_contem_chave44():
    xml = _montar()
    NS = 'http://www.portalfiscal.inf.br/nfe'
    root = etree.fromstring(xml.encode('utf-8'))
    inf = root.find(f'{{{NS}}}infNFe')
    assert inf.get('Id') == f'NFe{_CHAVE44}'


def test_namespace_sem_prefixo():
    """
    xsdata serializa com prefixo 'ns0:'. O builder deve produzir
    <NFe xmlns="..."><infNFe> sem prefixo — SEFAZ rejeita com prefixo.
    """
    xml = _montar()
    assert 'ns0:' not in xml, 'Namespace com prefixo ns0: encontrado no XML'
    assert 'xmlns=' in xml or 'xmlns:' not in xml.split('<NFe')[0]


def test_cpf_no_destinatario():
    xml = _montar()
    NS = 'http://www.portalfiscal.inf.br/nfe'
    root = etree.fromstring(xml.encode('utf-8'))
    dest = root.find(f'.//{{{NS}}}dest')
    cpf_el = dest.find(f'{{{NS}}}CPF')
    assert cpf_el is not None
    assert cpf_el.text == '12345678909'


def test_tp_amb_homologacao_no_xml():
    xml = _montar(config=_CONFIG_HOMOLOGACAO)
    NS = 'http://www.portalfiscal.inf.br/nfe'
    root = etree.fromstring(xml.encode('utf-8'))
    tp_amb = root.find(f'.//{{{NS}}}tpAmb')
    assert tp_amb.text == '2'


def test_tp_amb_producao_no_xml():
    xml = _montar(config=_CONFIG_PRODUCAO)
    NS = 'http://www.portalfiscal.inf.br/nfe'
    root = etree.fromstring(xml.encode('utf-8'))
    tp_amb = root.find(f'.//{{{NS}}}tpAmb')
    assert tp_amb.text == '1'


def test_v_nf_igual_ao_valor_do_pagamento():
    xml = _montar()
    NS = 'http://www.portalfiscal.inf.br/nfe'
    root = etree.fromstring(xml.encode('utf-8'))
    vnf = root.find(f'.//{{{NS}}}vNF')
    assert vnf is not None
    assert vnf.text == '97.00'
