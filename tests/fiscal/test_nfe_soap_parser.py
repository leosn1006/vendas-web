"""
Testes para _parsear_ret_envi_nfe — parser da resposta SOAP do SVRS.

Por que testar isso: se a SEFAZ mudar o formato da resposta ou se alguém
alterar o parser, os testes falham antes de afetar qualquer NF-e real.
Esses testes usam XML estático (sem chamada de rede) e cobrem os caminhos
principais que o código de produção percorre: autorizado, rejeitado, e resposta malformada.
"""
import pytest
from app.fiscal.nfe_soap import _parsear_ret_envi_nfe

NS = 'http://www.portalfiscal.inf.br/nfe'
NS_WSDL = 'http://www.portalfiscal.inf.br/nfe/wsdl/NFeAutorizacao4'
NS_SOAP = 'http://www.w3.org/2003/05/soap-envelope'


def _envelope(ret_envi_nfe_xml: str) -> str:
    return (
        f'<?xml version="1.0" encoding="utf-8"?>'
        f'<soap:Envelope xmlns:soap="{NS_SOAP}">'
        f'<soap:Body>'
        f'<nfeResultMsg xmlns="{NS_WSDL}">'
        f'{ret_envi_nfe_xml}'
        f'</nfeResultMsg>'
        f'</soap:Body>'
        f'</soap:Envelope>'
    )


def _ret_envi_nfe(c_stat: str, x_motivo: str, n_rec: str = '', prot_xml: str = '') -> str:
    return (
        f'<retEnviNFe versao="4.00" xmlns="{NS}">'
        f'<tpAmb>2</tpAmb>'
        f'<verAplic>SVRS202306</verAplic>'
        f'<cStat>{c_stat}</cStat>'
        f'<xMotivo>{x_motivo}</xMotivo>'
        f'<dhRecbto>2026-06-23T10:00:00-03:00</dhRecbto>'
        f'<nRec>{n_rec}</nRec>'
        f'{prot_xml}'
        f'</retEnviNFe>'
    )


def _prot_nfe(c_stat: str, x_motivo: str, n_prot: str = '153900000098765',
              chave: str = '53260664980953000146550010000000001162886597') -> str:
    return (
        f'<protNFe versao="4.00" xmlns="{NS}">'
        f'<infProt>'
        f'<tpAmb>2</tpAmb>'
        f'<verAplic>SVRS202306</verAplic>'
        f'<chNFe>{chave}</chNFe>'
        f'<dhRecbto>2026-06-23T10:00:00-03:00</dhRecbto>'
        f'<nProt>{n_prot}</nProt>'
        f'<digVal>abc123==</digVal>'
        f'<cStat>{c_stat}</cStat>'
        f'<xMotivo>{x_motivo}</xMotivo>'
        f'</infProt>'
        f'</protNFe>'
    )


# ─── Caminhos de sucesso ──────────────────────────────────────────────────────

def test_autorizada_c_stat_104_prot_100():
    """Caminho feliz: lote processado (104) + NF-e autorizada (100)."""
    prot = _prot_nfe('100', 'Autorizado o uso da NF-e', '153900000098765')
    xml = _envelope(_ret_envi_nfe('104', 'Lote processado', '153900000099999', prot))
    resultado = _parsear_ret_envi_nfe(xml)

    assert resultado['c_stat'] == '104'
    assert resultado['x_motivo'] == 'Lote processado'
    assert resultado['prot_c_stat'] == '100'
    assert resultado['n_prot'] == '153900000098765'
    assert resultado['prot_x_motivo'] == 'Autorizado o uso da NF-e'
    assert resultado['prot_nfe_xml'] != ''


def test_prot_nfe_xml_contem_tag_protNFe():
    prot = _prot_nfe('100', 'Autorizado o uso da NF-e')
    xml = _envelope(_ret_envi_nfe('104', 'Lote processado', prot_xml=prot))
    resultado = _parsear_ret_envi_nfe(xml)
    assert '<protNFe' in resultado['prot_nfe_xml']


# ─── Caminhos de rejeição ─────────────────────────────────────────────────────

def test_rejeitada_ie_invalida_c_stat_209():
    """cStat=209 que encontramos durante testes: IE do emitente inválida."""
    prot = _prot_nfe('209', 'Rejeicao: IE do Emitente nao cadastrada')
    xml = _envelope(_ret_envi_nfe('104', 'Lote processado', prot_xml=prot))
    resultado = _parsear_ret_envi_nfe(xml)

    assert resultado['prot_c_stat'] == '209'
    assert 'IE' in resultado['prot_x_motivo']


def test_rejeitada_xnome_homologacao_errado_c_stat_598():
    """cStat=598 quando xNome do destinatário em homologação está incorreto."""
    prot = _prot_nfe('598', 'Rejeicao: Identificacao do destinatario incorreta')
    xml = _envelope(_ret_envi_nfe('104', 'Lote processado', prot_xml=prot))
    resultado = _parsear_ret_envi_nfe(xml)
    assert resultado['prot_c_stat'] == '598'


def test_rejeitada_ind_intermed_ausente_c_stat_434():
    """cStat=434 quando indIntermed está ausente para indPres=2 (NT 2020.006)."""
    prot = _prot_nfe('434', 'Rejeicao: Uso indevido do Ambiente de Autorizacao')
    xml = _envelope(_ret_envi_nfe('104', 'Lote processado', prot_xml=prot))
    resultado = _parsear_ret_envi_nfe(xml)
    assert resultado['prot_c_stat'] == '434'


def test_rejeicao_nivel_lote_sem_prot():
    """Alguns cStats de rejeição chegam no nível do lote, sem protNFe."""
    xml = _envelope(_ret_envi_nfe('225', 'Rejeicao: Falha no schema XML'))
    resultado = _parsear_ret_envi_nfe(xml)

    assert resultado['c_stat'] == '225'
    assert resultado['prot_c_stat'] == ''
    assert resultado['prot_nfe_xml'] == ''


# ─── Respostas malformadas ────────────────────────────────────────────────────

def test_xml_invalido_retorna_dict_com_erro():
    resultado = _parsear_ret_envi_nfe('isso nao e xml')
    assert resultado['c_stat'] == ''
    assert 'inválida' in resultado['x_motivo'] or resultado['x_motivo'] != ''


def test_sem_ret_envi_nfe_retorna_dict_com_erro():
    xml = (
        '<?xml version="1.0"?>'
        f'<soap:Envelope xmlns:soap="{NS_SOAP}">'
        '<soap:Body><alguma_outra_tag/></soap:Body>'
        '</soap:Envelope>'
    )
    resultado = _parsear_ret_envi_nfe(xml)
    assert resultado['c_stat'] == ''
    assert 'retEnviNFe' in resultado['x_motivo']


def test_n_rec_extraido_corretamente():
    xml = _envelope(_ret_envi_nfe('103', 'Lote recebido com sucesso', n_rec='153900123456789'))
    resultado = _parsear_ret_envi_nfe(xml)
    assert resultado['n_rec'] == '153900123456789'


def test_campos_ausentes_retornam_string_vazia():
    """
    Mesmo em erro de parse, o dict sempre retorna todas as chaves esperadas.
    Isso evita KeyError no _processar_retorno em caso de resposta inesperada da SEFAZ.
    """
    resultado = _parsear_ret_envi_nfe('nao xml')
    campos_obrigatorios = ('c_stat', 'x_motivo', 'n_rec', 'prot_c_stat', 'prot_x_motivo', 'n_prot')
    for campo in campos_obrigatorios:
        assert campo in resultado, f"Campo '{campo}' ausente no dict de erro"
        assert isinstance(resultado[campo], str)
    assert resultado['c_stat'] == ''
    assert resultado['x_motivo'] != ''  # deve ter mensagem de erro
