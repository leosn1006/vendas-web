"""
Monta o XML infNFe 4.00 usando nfelib dataclasses.

Tributação confirmada pelo contador para livros digitais com ISBN (Lucro Presumido):
  ICMS  CST 40 — Isento (imunidade constitucional, art. 150 VI d CF/88)
  PIS   CST 06 — Operação Tributável a Alíquota Zero
  COFINS CST 06 — Operação Tributável a Alíquota Zero
"""
from datetime import datetime
from decimal import Decimal

from lxml import etree
from xsdata.formats.dataclass.serializers import XmlSerializer
from xsdata.formats.dataclass.context import XmlContext
from xsdata.formats.dataclass.serializers.config import SerializerConfig

from nfelib.nfe.bindings.v4_0.leiaute_nfe_v4_00 import (
    Tnfe, TenderEmi, Tendereco, TufEmi, Tuf,
    TcodUfIbge, Tmod, Tamb, TfinNfe, Torig,
    EmitCrt, DestIndIedest, TranspModFrete,
    IdeTpNf, IdeIdDest, IdeTpImp, IdeTpEmis, IdeIndFinal, IdeIndPres, IdeIndIntermed,
    Icms40Cst, Icms40MotDesIcms, PisntCst, CofinsntCst,
)

_ZERO = '0.00'

# Dados fixos do emitente (DF)
_EMIT = {
    'cnpj':         '64980953000146',
    'razao_social': 'LEONARDO SANTOS NEGREIROS',
    'nome_fantasia': 'LSN LIVROS',
    'ie':           'ISENTO',          # preencher com IE real do DF quando obtida
    'crt':          '3',               # Lucro Presumido
    'logradouro':   'SHA Conjunto 4 Chacara 19 Lote C',
    'numero':       '5',
    'bairro':       'Arniqueira',
    'c_mun':        '5300108',         # IBGE Brasília/DF
    'x_mun':        'Brasilia',
    'uf':           'DF',
    'cep':          '71994120',
}

NS = 'http://www.portalfiscal.inf.br/nfe'

_SER = XmlSerializer(
    context=XmlContext(),
    config=SerializerConfig(pretty_print=False),
)


def _fmt_valor(v) -> str:
    return f'{Decimal(str(v)):.2f}'


def _endereco_emitente(e: dict) -> TenderEmi:
    return TenderEmi(
        xLgr=e['logradouro'],
        nro=e['numero'],
        xBairro=e['bairro'],
        cMun=e['c_mun'],
        xMun=e['x_mun'],
        UF=TufEmi(e['uf']),
        CEP=e['cep'],
    )


def _endereco_dest_fallback(e: dict) -> Tendereco:
    """Endereço do emitente como fallback para o destinatário B2C (sem entrega física)."""
    return Tendereco(
        xLgr=e['logradouro'],
        nro=e['numero'],
        xBairro=e['bairro'],
        cMun=e['c_mun'],
        xMun=e['x_mun'],
        UF=Tuf(e['uf']),
        CEP=e['cep'],
    )


def _icms_livro() -> Tnfe.InfNfe.Det.Imposto.Icms:
    # CST 41 = Não tributado — imunidade constitucional art. 150 VI d (livros com ISBN)
    # motDesICMS=90 (Outros) + vICMSDeson=0 exigidos pelo DF quando cBenef informado
    return Tnfe.InfNfe.Det.Imposto.Icms(
        ICMS40=Tnfe.InfNfe.Det.Imposto.Icms.Icms40(
            orig=Torig('0'),
            CST=Icms40Cst('41'),
            vICMSDeson=_ZERO,
            motDesICMS=Icms40MotDesIcms('90'),
        )
    )


def _pis_livro() -> Tnfe.InfNfe.Det.Imposto.Pis:
    # CST 06 = Operação Tributável a Alíquota Zero (livros com ISBN)
    return Tnfe.InfNfe.Det.Imposto.Pis(
        PISNT=Tnfe.InfNfe.Det.Imposto.Pis.Pisnt(
            CST=PisntCst('06'),
        )
    )


def _cofins_livro() -> Tnfe.InfNfe.Det.Imposto.Cofins:
    # CST 06 = Operação Tributável a Alíquota Zero (livros com ISBN)
    return Tnfe.InfNfe.Det.Imposto.Cofins(
        COFINSNT=Tnfe.InfNfe.Det.Imposto.Cofins.Cofinsnt(
            CST=CofinsntCst('06'),
        )
    )


def montar_nfe(
    config: dict,
    pagamento: dict,
    n_nf: int,
    chave44: str,
    c_nf: str,
    data_emissao: datetime | None = None,
) -> str:
    """
    Monta e serializa o XML da NF-e 4.00 (ainda não assinado).

    Args:
        config:       dict de nfe_configuracao (serie_padrao, ambiente, x_prod, ncm, cfop)
        pagamento:    dict de pagamento_pix (cpf_cnpj, nome_pagador, valor)
        n_nf:         número sequencial da NF-e
        chave44:      chave de acesso de 44 dígitos já calculada
        c_nf:         código numérico aleatório de 8 dígitos (parte da chave)
        data_emissao: datetime da emissão (default: agora)

    Returns:
        XML string sem declaração <?xml?> e sem assinatura.
    """
    if data_emissao is None:
        data_emissao = datetime.now()

    tp_amb   = str(config.get('ambiente', 2))
    # XSD aceita série sem zeros à esquerda: padrão '0|[1-9][0-9]{0,2}'
    # Na chave de acesso usa-se zfill(3), mas no elemento XML o valor é numérico
    serie    = str(int(config.get('serie_padrao', '1')))
    x_prod   = config.get('x_prod', 'Livro Digital')
    ncm      = config.get('ncm') or '49011000'   # livro digital — VALIDAR COM CONTADOR
    cfop     = config.get('cfop') or '5102'       # venda de mercadoria a não-contribuinte (confirmar com contador)
    c_benef  = config.get('c_benef') or None      # cBenef obrigatório quando CST=40 — ex: DF811004 (livros DF)
    valor    = _fmt_valor(pagamento.get('valor', '0'))
    cpf_cnpj = ''.join(filter(str.isdigit, str(pagamento.get('cpf_cnpj') or '')))
    # Homologação exige xNome exato do destinatário (cStat=598 se diferente)
    if int(tp_amb) == 2:
        nome = 'NF-E EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL'
    else:
        nome = (pagamento.get('nome_pagador') or 'CONSUMIDOR')[:60]
    dh_emi   = data_emissao.strftime('%Y-%m-%dT%H:%M:%S') + '-03:00'

    nfe_id = f'NFe{chave44}'

    # Dados do emitente: config (nfe_configuracao) tem precedência sobre _EMIT hardcoded.
    # Todos os campos relevantes devem estar preenchidos no banco para multi-tenant.
    emit_data = {
        'cnpj':         config.get('cnpj')         or _EMIT['cnpj'],
        'razao_social': config.get('razao_social')  or _EMIT['razao_social'],
        'nome_fantasia': config.get('nome_fantasia') or _EMIT['nome_fantasia'],
        'crt':          str(config.get('crt')       or _EMIT['crt']),
        'ie':           config.get('ie')            or _EMIT['ie'],
        'logradouro':   config.get('logradouro')    or _EMIT['logradouro'],
        'numero':       config.get('numero')        or _EMIT['numero'],
        'bairro':       config.get('bairro')        or _EMIT['bairro'],
        'c_mun':        str(config.get('c_mun')     or _EMIT['c_mun']),
        'x_mun':        config.get('x_mun')         or _EMIT['x_mun'],
        'uf':           config.get('uf')            or _EMIT['uf'],
        'cep':          config.get('cep')           or _EMIT['cep'],
    }

    emit = Tnfe.InfNfe.Emit(
        CNPJ=emit_data['cnpj'],
        xNome=emit_data['razao_social'],
        xFant=emit_data['nome_fantasia'],
        enderEmit=_endereco_emitente(emit_data),
        IE=emit_data['ie'],
        CRT=EmitCrt(emit_data['crt']),
    )

    # Destinatário B2C: CPF ou CNPJ conforme tamanho
    dest_kwargs = {
        'xNome':     nome,
        'enderDest': _endereco_dest_fallback(emit_data),
        'indIEDest': DestIndIedest('9'),  # 9 = Não contribuinte
    }
    if len(cpf_cnpj) == 11:
        dest_kwargs['CPF'] = cpf_cnpj
    elif len(cpf_cnpj) == 14:
        dest_kwargs['CNPJ'] = cpf_cnpj
    # sem CPF/CNPJ: campo omitido (PIX sem identificação)

    dest = Tnfe.InfNfe.Dest(**dest_kwargs)

    det = Tnfe.InfNfe.Det(
        nItem='1',
        prod=Tnfe.InfNfe.Det.Prod(
            cProd='001',
            cEAN='SEM GTIN',
            xProd=x_prod,
            NCM=ncm,
            cBenef=c_benef,
            CFOP=cfop,
            uCom='UN',
            qCom='1.0000',
            vUnCom=valor,
            vProd=valor,
            cEANTrib='SEM GTIN',
            uTrib='UN',
            qTrib='1.0000',
            vUnTrib=valor,
            indTot='1',
        ),
        imposto=Tnfe.InfNfe.Det.Imposto(
            ICMS=_icms_livro(),
            PIS=_pis_livro(),
            COFINS=_cofins_livro(),
        ),
    )

    icms_tot = Tnfe.InfNfe.Total.Icmstot(
        vBC=_ZERO, vICMS=_ZERO, vICMSDeson=_ZERO,
        vFCPUFDest=_ZERO, vICMSUFDest=_ZERO, vICMSUFRemet=_ZERO,
        vFCP=_ZERO, vBCST=_ZERO, vST=_ZERO, vFCPST=_ZERO, vFCPSTRet=_ZERO,
        vProd=valor, vFrete=_ZERO, vSeg=_ZERO, vDesc=_ZERO,
        vII=_ZERO, vIPI=_ZERO, vIPIDevol=_ZERO,
        vPIS=_ZERO, vCOFINS=_ZERO, vOutro=_ZERO,
        vNF=valor,
    )

    pag = Tnfe.InfNfe.Pag(
        detPag=[
            Tnfe.InfNfe.Pag.DetPag(
                tPag='17',   # 17 = PIX
                vPag=valor,
            )
        ]
    )

    inf_nfe = Tnfe.InfNfe(
        versao='4.00',
        Id=nfe_id,
        ide=Tnfe.InfNfe.Ide(
            cUF=TcodUfIbge('53'),
            cNF=c_nf,
            natOp='VENDA DE PRODUTO DIGITAL',
            mod=Tmod('55'),
            serie=serie,
            nNF=str(n_nf),
            dhEmi=dh_emi,
            tpNF=IdeTpNf('1'),           # 1 = Saída
            idDest=IdeIdDest('1'),        # 1 = Interna (endereço emitente como fallback — sem endereço real do cliente)
            cMunFG=emit_data['c_mun'],
            tpImp=IdeTpImp('1'),          # 1 = DANFE normal
            tpEmis=IdeTpEmis('1'),        # 1 = Emissão normal
            cDV=chave44[-1],
            tpAmb=Tamb(tp_amb),
            finNFe=TfinNfe('1'),          # 1 = NF-e normal
            indFinal=IdeIndFinal('1'),        # 1 = Consumidor final
            indPres=IdeIndPres('2'),          # 2 = Operação não presencial, pela Internet
            indIntermed=IdeIndIntermed('0'),  # 0 = Sem intermediador (venda no próprio site)
            procEmi='0',                      # 0 = Aplicativo do contribuinte
            verProc='1.0.0',
        ),
        emit=emit,
        dest=dest,
        det=[det],
        total=Tnfe.InfNfe.Total(ICMSTot=icms_tot),
        transp=Tnfe.InfNfe.Transp(
            modFrete=TranspModFrete('9'),  # 9 = Sem frete (produto digital)
        ),
        pag=pag,
    )

    nfe_obj = Tnfe(infNFe=inf_nfe)
    xml_raw = _SER.render(nfe_obj)

    # xsdata serializa como <TNFe><ns0:infNFe xmlns:ns0="...">
    # Precisamos de <NFe xmlns="..."><infNFe ...> (namespace padrão, sem prefixo)
    doc = etree.fromstring(xml_raw.encode())
    inf_el = doc.find(f'{{{NS}}}infNFe')
    nfe_root = etree.Element(f'{{{NS}}}NFe', nsmap={None: NS})
    nfe_root.append(inf_el)
    return etree.tostring(nfe_root, encoding='unicode', xml_declaration=False)
