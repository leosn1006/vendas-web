import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'app'))

import pytest

import certificados_ssl
import config


def _ok(dominio, dias):
    return {'dominio': dominio, 'vence_em': datetime(2027, 1, 1, tzinfo=timezone.utc), 'dias': dias}


@pytest.fixture
def consultas(monkeypatch):
    respostas = {}
    monkeypatch.setattr(certificados_ssl, 'consultar', lambda d: respostas[d])
    return respostas


@pytest.fixture
def enviados():
    lista = []
    return lista, lambda **kw: lista.append(kw)


def test_sem_alerta_nao_envia(consultas, enviados, monkeypatch):
    monkeypatch.setattr(config, 'EH_PRODUCAO', True)
    consultas.update({'a.site': _ok('a.site', 60), 'b.site': _ok('b.site', 21)})
    lista, enviar = enviados
    assert certificados_ssl.verificar_certificados(['a.site', 'b.site'], enviar_email=enviar) == []
    assert lista == []


def test_alerta_com_20_dias_e_certificado_invalido(consultas, enviados, monkeypatch):
    monkeypatch.setattr(config, 'EH_PRODUCAO', True)
    consultas.update({'a.site': _ok('a.site', 20), 'b.site': {'dominio': 'b.site', 'erro': 'certificate has expired'},
                      'c.site': _ok('c.site', 45)})
    lista, enviar = enviados
    alertas = certificados_ssl.verificar_certificados(['a.site', 'b.site', 'c.site'], enviar_email=enviar)
    assert [a['dominio'] for a in alertas] == ['a.site', 'b.site']
    assert len(lista) == 1
    assert lista[0]['destinatario'] == 'admin@lsnlivros.com.br'
    assert '2 certificado(s)' in lista[0]['subject']
    assert 'a.site' in lista[0]['html'] and 'certificate has expired' in lista[0]['html']
    assert 'c.site' not in lista[0]['html']


def test_dominio_do_bb_aparece_como_manual(consultas, enviados, monkeypatch):
    monkeypatch.setattr(config, 'EH_PRODUCAO', True)
    consultas['lsnlivros.com.br'] = _ok('lsnlivros.com.br', 10)
    lista, enviar = enviados
    certificados_ssl.verificar_certificados(['lsnlivros.com.br'], enviar_email=enviar)
    assert 'manual (BB)' in lista[0]['html']


def test_dev_nao_envia(consultas, enviados, monkeypatch):
    monkeypatch.setattr(config, 'EH_PRODUCAO', False)
    consultas['a.site'] = _ok('a.site', 5)
    lista, enviar = enviados
    assert len(certificados_ssl.verificar_certificados(['a.site'], enviar_email=enviar)) == 1
    assert lista == []
