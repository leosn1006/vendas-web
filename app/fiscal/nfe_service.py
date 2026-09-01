"""
Orquestrador de emissão de NF-e.

Fluxo:
  1. Busca config (nfe_configuracao) e pagamento_pix
  2. Idempotência: pagamento_pix.nfe_emitida_id já preenchido → retorna sem reemitir
  3. Reserva próximo número (SELECT … FOR UPDATE)
  4. Gera chave de acesso (44 dígitos, cDV mod11)
  5. Monta XML infNFe com nfelib
  6. Assina XML (RSA-SHA1, enveloped, C14N 1.0)
  7. Valida XSD contra nfe_v4.00.xsd do nfelib
  8. Salva em nfe_emitidas (status=enviando)
  9. Envia lote individual (indSinc=1) para NFeAutorizacao4
 10. Processa retorno: autoriza, rejeita ou agenda consulta
 11. Grava log SOAP (sem senha do certificado)
"""
import os
import logging
from datetime import datetime

from mysql.connector import IntegrityError

from database import (
    buscar_nfe_configuracao_ativa,
    buscar_pagamento_pix_por_id,
    incrementar_numero_nfe,
    criar_nfe_pendente,
    vincular_nfe_ao_pagamento_pix,
    atualizar_nfe_autorizada,
    atualizar_nfe_rejeitada,
    atualizar_nfe_aguardando_retorno,
    atualizar_nfe_erro,
    gravar_log_soap,
)
from fiscal.certificado import certificado_temp
from fiscal.nfe_chave import gerar_chave
from fiscal.nfe_xml_builder import montar_nfe
from fiscal.nfe_assinador import assinar_nfe
from fiscal.nfe_validador import validar_nfe
from fiscal.nfe_soap import enviar_autorizacao

logger = logging.getLogger(__name__)

_C_UF_DF = '53'


def emitir_nfe(pagamento_pix_id: int, config_id: int | None = None) -> dict:
    """
    Emite uma NF-e para um pagamento PIX.

    Args:
        pagamento_pix_id: PK de pagamento_pix
        config_id: tenant específico; None usa o tenant ativo padrão

    Returns dict com:
        status: 'autorizada' | 'rejeitada' | 'aguardando_retorno' | 'ja_emitida'
        nfe_id: id em nfe_emitidas
        c_stat, x_motivo: retorno SEFAZ (quando disponível)
        n_prot: número do protocolo (quando autorizada)
    """
    # 1. Configuração
    config = (
        buscar_nfe_configuracao_ativa()
        if config_id is None
        else _buscar_config_por_id(config_id)
    )
    if not config:
        raise RuntimeError('Nenhuma configuração NF-e ativa encontrada')

    # 2. Pagamento PIX
    pix = buscar_pagamento_pix_por_id(pagamento_pix_id)
    if not pix:
        raise ValueError(f'pagamento_pix {pagamento_pix_id} não encontrado')

    # 3. Idempotência
    if pix.get('nfe_emitida_id'):
        logger.info(f'[NF-e] PIX {pagamento_pix_id} já tem nfe_id={pix["nfe_emitida_id"]}')
        return {'status': 'ja_emitida', 'nfe_id': pix['nfe_emitida_id']}

    # 4. Valida env var da senha e existência do cert antes de reservar número
    senha = os.getenv(config['certificado_senha_env'], '')
    if not senha:
        raise RuntimeError(
            f'Variável {config["certificado_senha_env"]} não definida no ambiente'
        )
    if not os.path.exists(config['certificado_path']):
        raise RuntimeError(
            f'Certificado não encontrado: {config["certificado_path"]}'
        )

    # 5. Reserva número com lock (transação própria, commita antes do SOAP)
    n_nf = incrementar_numero_nfe(config['id'])
    serie = config.get('serie_padrao', '001')
    data_emissao = datetime.now()
    ambiente = int(config.get('ambiente', 2))

    # 6. Gera chave de acesso
    chave44, c_nf = gerar_chave(_C_UF_DF, data_emissao, config['cnpj'], '55', serie, n_nf)

    logger.info(f'[NF-e] Emitindo NF-e #{n_nf} chave={chave44} PIX={pagamento_pix_id}')

    soap_req = soap_resp = ''
    status_http = 0
    duracao_ms  = 0.0
    nfe_id = None

    try:
        with certificado_temp(config['certificado_path'], senha) as (cert_path, key_path, _):
            with open(cert_path, 'rb') as f:
                cert_pem = f.read()
            with open(key_path, 'rb') as f:
                key_pem = f.read()

            # 7. Monta e assina XML
            xml          = montar_nfe(config, pix, n_nf, chave44, c_nf, data_emissao)
            xml_assinado = assinar_nfe(xml, key_pem, cert_pem)

            # 8. Valida XSD — rejeita antes de comunicar com a SEFAZ
            erros_xsd = validar_nfe(xml_assinado)
            if erros_xsd:
                raise ValueError(f'XML inválido (XSD): {erros_xsd[0]}')

            # 9. Salva como 'enviando'
            try:
                nfe_id = criar_nfe_pendente(
                    config['id'], pagamento_pix_id, chave44,
                    str(n_nf), serie, ambiente,
                    xml_assinado.decode('utf-8'),
                )
            except IntegrityError:
                # Race condition: outra task criou o registro antes
                logger.info(f'[NF-e] PIX {pagamento_pix_id} já processado por task concorrente')
                return {'status': 'ja_emitida', 'nfe_id': None}

            # 10. Envia para SEFAZ
            # Em homologação: verify=False (CA ICP-Brasil não está no bundle padrão do Python)
            # Em produção: passar o caminho do CA bundle ICP-Brasil via nfe_configuracao.ca_bundle_path
            # (campo a adicionar na migration quando for a produção)
            ca_bundle_path = config.get('ca_bundle_path') or None
            if ca_bundle_path:
                ca_bundle = ca_bundle_path        # CA bundle ICP-Brasil explícito
            else:
                ca_bundle = False                 # ICP-Brasil não está no bundle padrão do Python
            result = enviar_autorizacao(
                xml_nfe_assinado=xml_assinado,
                cert_path=cert_path,
                key_path=key_path,
                ambiente=ambiente,
                verify=ca_bundle,
            )

        soap_req    = result['soap_request']
        soap_resp   = result['soap_response']
        status_http = result['status_http']
        duracao_ms  = result['duracao_ms']

        # 11. Processa retorno
        retorno = _processar_retorno(nfe_id, result, xml_assinado, pagamento_pix_id)

    except Exception as e:
        logger.exception(f'[NF-e] Erro ao emitir NF-e PIX={pagamento_pix_id}: {e}')
        if nfe_id:
            atualizar_nfe_erro(nfe_id, str(e))
            gravar_log_soap(nfe_id, 'autorizacao', '', soap_req, soap_resp,
                            status_http, duracao_ms)
        raise

    gravar_log_soap(
        nfe_id, 'autorizacao', result.get('url', ''),
        soap_req, soap_resp, status_http, duracao_ms,
    )
    return retorno


def _processar_retorno(
    nfe_id: int,
    result: dict,
    xml_assinado: bytes,
    pagamento_pix_id: int,
) -> dict:
    """Interpreta cStat do retorno SVRS e salva o estado final."""
    c_stat   = result['c_stat']
    x_motivo = result['x_motivo']

    # cStat=104: lote processado — verificar protNFe dentro do retorno
    if c_stat == '104':
        prot_c_stat  = result.get('prot_c_stat', '')
        prot_motivo  = result.get('prot_x_motivo', '')
        n_prot       = result.get('n_prot', '')
        dh_recbto    = result.get('dh_recbto', '')
        prot_xml     = result.get('prot_nfe_xml', '')

        if prot_c_stat == '100':
            nfe_proc = _montar_nfe_proc(xml_assinado, prot_xml)
            atualizar_nfe_autorizada(nfe_id, prot_c_stat, prot_motivo, n_prot, dh_recbto, nfe_proc)
            vincular_nfe_ao_pagamento_pix(pagamento_pix_id, nfe_id)
            logger.info(f'[NF-e] {nfe_id} autorizada — nProt={n_prot}')
            return {
                'status': 'autorizada', 'nfe_id': nfe_id,
                'c_stat': prot_c_stat, 'x_motivo': prot_motivo, 'n_prot': n_prot,
            }

        # cStat dentro de protNFe ≠ 100 → rejeição (cStat ≥ 200)
        atualizar_nfe_rejeitada(nfe_id, prot_c_stat, prot_motivo)
        logger.warning(f'[NF-e] {nfe_id} rejeitada — cStat={prot_c_stat} {prot_motivo}')
        return {
            'status': 'rejeitada', 'nfe_id': nfe_id,
            'c_stat': prot_c_stat, 'x_motivo': prot_motivo,
        }

    # cStat=103: recebida para processamento assíncrono (não deve ocorrer com indSinc=1)
    if c_stat == '103':
        n_rec = result.get('n_rec', '')
        atualizar_nfe_aguardando_retorno(nfe_id, n_rec)
        logger.info(f'[NF-e] {nfe_id} aguardando retorno — nRec={n_rec}')
        return {
            'status': 'aguardando_retorno', 'nfe_id': nfe_id,
            'c_stat': c_stat, 'x_motivo': x_motivo, 'n_rec': n_rec,
        }

    # Qualquer outro cStat no nível do lote é rejeição (ex: 108, 215, 225, 539…)
    atualizar_nfe_rejeitada(nfe_id, c_stat, x_motivo)
    logger.warning(f'[NF-e] {nfe_id} lote rejeitado — cStat={c_stat} {x_motivo}')
    return {
        'status': 'rejeitada', 'nfe_id': nfe_id,
        'c_stat': c_stat, 'x_motivo': x_motivo,
    }


def _montar_nfe_proc(xml_assinado: bytes, prot_nfe_xml: str) -> str:
    """Combina <NFe> assinada + <protNFe> em <nfeProc>."""
    ns = 'http://www.portalfiscal.inf.br/nfe'
    nfe_str = xml_assinado.decode('utf-8') if isinstance(xml_assinado, bytes) else xml_assinado
    return (
        f'<nfeProc versao="4.00" xmlns="{ns}">'
        f'{nfe_str}'
        f'{prot_nfe_xml}'
        '</nfeProc>'
    )


def _buscar_config_por_id(config_id: int) -> dict | None:
    from database import db
    return db.execute_query(
        "SELECT * FROM nfe_configuracao WHERE id = %s AND ativo = 1",
        (config_id,), fetch_one=True,
    )
