import time
import logging
import requests
from .certificado import certificado_temp

logger = logging.getLogger(__name__)

ENDPOINTS = {
    'homologacao': {
        'status':         'https://nfe-homologacao.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx',
        'autorizacao':    'https://nfe-homologacao.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx',
        'ret_autorizacao':'https://nfe-homologacao.svrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx',
        'consulta':       'https://nfe-homologacao.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx',
        'eventos':        'https://nfe-homologacao.svrs.rs.gov.br/ws/recepcaoevento/recepcaoevento4.asmx',
        'inutilizacao':   'https://nfe-homologacao.svrs.rs.gov.br/ws/NfeInutilizacao/NfeInutilizacao4.asmx',
    },
    'producao': {
        'status':         'https://nfe.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx',
        'autorizacao':    'https://nfe.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx',
        'ret_autorizacao':'https://nfe.svrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx',
        'consulta':       'https://nfe.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx',
        'eventos':        'https://nfe.svrs.rs.gov.br/ws/recepcaoevento/recepcaoevento4.asmx',
        'inutilizacao':   'https://nfe.svrs.rs.gov.br/ws/NfeInutilizacao/NfeInutilizacao4.asmx',
    },
}

# cUF do Distrito Federal
C_UF_DF = '53'

_SOAP_ACTIONS = {
    'status':         'http://www.portalfiscal.inf.br/nfe/wsdl/NFeStatusServico4/nfeStatusServicoNF',
    'autorizacao':    'http://www.portalfiscal.inf.br/nfe/wsdl/NFeAutorizacao4/nfeAutorizacaoNF',
    'ret_autorizacao':'http://www.portalfiscal.inf.br/nfe/wsdl/NFeRetAutorizacao4/nfeRetAutorizacaoNF',
    'consulta':       'http://www.portalfiscal.inf.br/nfe/wsdl/NFeConsulta4/nfeConsultaNF',
}

# Namespace WSDL por operação (cabecMsg e dadosMsg)
_WSDL_SVC = {
    'status':         'NFeStatusServico4',
    'autorizacao':    'NFeAutorizacao4',
    'ret_autorizacao':'NFeRetAutorizacao4',
    'consulta':       'NFeConsulta4',
}


def _envelope_soap(cabec_xml: str, corpo_xml: str, wsdl_svc: str) -> str:
    ns = f'http://www.portalfiscal.inf.br/nfe/wsdl/{wsdl_svc}'
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<soap12:Envelope '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
        'xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">'
        '<soap12:Header>'
        f'<nfeCabecMsg xmlns="{ns}">'
        f'{cabec_xml}'
        '</nfeCabecMsg>'
        '</soap12:Header>'
        '<soap12:Body>'
        f'<nfeDadosMsg xmlns="{ns}">'
        f'{corpo_xml}'
        '</nfeDadosMsg>'
        '</soap12:Body>'
        '</soap12:Envelope>'
    )


def _chamar_servico(
    operacao: str,
    cabec_xml: str,
    corpo_xml: str,
    cert_path: str,
    key_path: str,
    ambiente: int,
    verify=True,
) -> tuple[str, str, int, float]:
    """
    Envia envelope SOAP e retorna (response_text, envelope, status_http, duracao_ms).
    Lança exceção em caso de erro de rede ou HTTP ≠ 200.

    verify: True (padrão), False (ignorar SSL — só testes locais),
            ou caminho para CA bundle ICP-Brasil em produção.
    """
    env_key = 'homologacao' if ambiente == 2 else 'producao'
    url = ENDPOINTS[env_key][operacao]
    envelope = _envelope_soap(cabec_xml, corpo_xml, _WSDL_SVC[operacao])

    headers = {
        'Content-Type': 'application/soap+xml; charset=UTF-8',
        'SOAPAction':   f'"{_SOAP_ACTIONS[operacao]}"',
    }

    if verify is False:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    inicio = time.monotonic()
    resp = requests.post(
        url,
        data=envelope.encode('utf-8'),
        headers=headers,
        cert=(cert_path, key_path),
        verify=verify,
        timeout=30,
    )
    duracao_ms = (time.monotonic() - inicio) * 1000

    logger.debug(f'[NF-e SOAP] {operacao} HTTP {resp.status_code} ({duracao_ms:.0f}ms)')
    resp.raise_for_status()
    return resp.text, envelope, resp.status_code, duracao_ms


def consultar_status_servico(cert_pfx: str, cert_senha: str, ambiente: int = 2, verify=True) -> dict:
    """
    Consulta NfeStatusServico4 e retorna dict com cStat, xMotivo e dhRecbto.
    ambiente: 1=produção, 2=homologação
    """
    tp_amb = str(ambiente)

    cabec = (
        f'<cUF>{C_UF_DF}</cUF>'
        f'<versaoDados>4.00</versaoDados>'
    )
    corpo = (
        '<consStatServ xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">'
        f'<tpAmb>{tp_amb}</tpAmb>'
        f'<cUF>{C_UF_DF}</cUF>'
        '<xServ>STATUS</xServ>'
        '</consStatServ>'
    )

    with certificado_temp(cert_pfx, cert_senha) as (cert_path, key_path, _):
        texto, _, status_http, duracao_ms = _chamar_servico(
            'status', cabec, corpo, cert_path, key_path, ambiente, verify=verify
        )

    # extrai cStat e xMotivo do XML de retorno
    c_stat  = _extrair_tag(texto, 'cStat')
    x_motivo = _extrair_tag(texto, 'xMotivo')
    dh_recbto = _extrair_tag(texto, 'dhRecbto')

    logger.info(f'[NF-e] Status SVRS: cStat={c_stat} xMotivo={x_motivo}')
    return {
        'cStat':    c_stat,
        'xMotivo':  x_motivo,
        'dhRecbto': dh_recbto,
        'status_http': status_http,
        'duracao_ms':  duracao_ms,
    }


def _extrair_tag(xml: str, tag: str) -> str:
    """Extração simples de conteúdo de tag XML sem parser completo."""
    inicio = xml.find(f'<{tag}>')
    if inicio == -1:
        return ''
    inicio += len(tag) + 2
    fim = xml.find(f'</{tag}>', inicio)
    return xml[inicio:fim] if fim != -1 else ''


def _parsear_ret_envi_nfe(xml_resp: str) -> dict:
    """Extrai dados estruturados do retorno de autorização NF-e."""
    from lxml import etree
    NS = 'http://www.portalfiscal.inf.br/nfe'
    P  = f'{{{NS}}}'

    def _t(el, tag):
        found = el.find(tag)
        return found.text or '' if found is not None else ''

    _vazio = {
        'c_stat': '', 'x_motivo': '', 'n_rec': '', 'dh_recbto': '',
        'prot_c_stat': '', 'prot_x_motivo': '', 'n_prot': '', 'prot_nfe_xml': '',
    }

    try:
        root = etree.fromstring(xml_resp.encode('utf-8'))
    except etree.XMLSyntaxError as e:
        return {**_vazio, 'x_motivo': f'Resposta inválida: {e}'}

    ret = root.find(f'.//{P}retEnviNFe')
    if ret is None:
        return {**_vazio, 'x_motivo': 'retEnviNFe não encontrado'}

    result = {
        'c_stat':        _t(ret, f'{P}cStat'),
        'x_motivo':      _t(ret, f'{P}xMotivo'),
        'n_rec':         _t(ret, f'{P}nRec'),
        'dh_recbto':     _t(ret, f'{P}dhRecbto'),
        'prot_c_stat':   '',
        'prot_x_motivo': '',
        'n_prot':        '',
        'prot_nfe_xml':  '',
    }

    prot = ret.find(f'{P}protNFe')
    if prot is not None:
        inf = prot.find(f'{P}infProt')
        if inf is not None:
            result['prot_c_stat']   = _t(inf, f'{P}cStat')
            result['prot_x_motivo'] = _t(inf, f'{P}xMotivo')
            result['n_prot']        = _t(inf, f'{P}nProt')
            result['dh_recbto']     = _t(inf, f'{P}dhRecbto') or result['dh_recbto']
        result['prot_nfe_xml'] = etree.tostring(prot, encoding='unicode')

    return result


def enviar_autorizacao(
    xml_nfe_assinado: bytes,
    cert_path: str,
    key_path: str,
    ambiente: int = 2,
    verify=True,
) -> dict:
    """
    Envia lote individual (indSinc=1) para NFeAutorizacao4 e retorna dict estruturado.

    Retorna:
        c_stat, x_motivo, n_rec, dh_recbto         — nível do lote (retEnviNFe)
        prot_c_stat, prot_x_motivo, n_prot          — nível da NF-e (protNFe.infProt)
        prot_nfe_xml                                 — XML do protNFe (para montar nfeProc)
        soap_request, soap_response, status_http, duracao_ms, url
    """
    nfe_xml_str = (
        xml_nfe_assinado.decode('utf-8')
        if isinstance(xml_nfe_assinado, bytes)
        else xml_nfe_assinado
    )

    id_lote = str(int(time.time() * 1000))[-15:]
    cabec = f'<cUF>{C_UF_DF}</cUF><versaoDados>4.00</versaoDados>'
    corpo = (
        f'<enviNFe xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">'
        f'<idLote>{id_lote}</idLote>'
        f'<indSinc>1</indSinc>'
        f'{nfe_xml_str}'
        f'</enviNFe>'
    )

    texto, envelope, status_http, duracao_ms = _chamar_servico(
        'autorizacao', cabec, corpo, cert_path, key_path, ambiente, verify=verify
    )
    url = ENDPOINTS['homologacao' if ambiente == 2 else 'producao']['autorizacao']

    parsed = _parsear_ret_envi_nfe(texto)
    parsed.update({
        'soap_request':  envelope,
        'soap_response': texto,
        'status_http':   status_http,
        'duracao_ms':    duracao_ms,
        'url':           url,
    })
    logger.info(
        f'[NF-e] autorizacao: cStat={parsed["c_stat"]} '
        f'protCStat={parsed["prot_c_stat"]} ({duracao_ms:.0f}ms)'
    )
    return parsed
