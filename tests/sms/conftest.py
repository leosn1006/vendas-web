"""SMS e link curto: imports como no container (app/ na raiz)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'app'))

import itertools  # noqa: E402
import re  # noqa: E402

import pytest  # noqa: E402


class BancoFalso:
    """O pouco de SQL que links_curtos e sms.servico usam, em memória (casado pelo começo da consulta)."""

    def __init__(self):
        self.links, self.acessos, self.envios = {}, [], {}
        self._ids = itertools.count(1)

    def execute_query(self, sql, params=(), fetch_one=False, fetch_all=False, return_rowcount=False):
        sql = ' '.join(sql.split())
        if sql.startswith('INSERT INTO links_curtos ('):
            codigo, url, origem, ref_tipo, ref_id, expira = params
            if any(l['codigo'] == codigo for l in self.links.values()):
                raise Exception('Duplicate entry')
            i = next(self._ids)
            self.links[i] = {'id': i, 'codigo': codigo, 'url_destino': url, 'origem': origem, 'ref_tipo': ref_tipo,
                             'ref_id': ref_id, 'cliques_humanos': 0, 'primeiro_clique_em': None}
            return i
        if sql.startswith('SELECT id, url_destino FROM links_curtos'):
            return next((l for l in self.links.values() if l['codigo'] == params[0]), None)
        if sql.startswith('INSERT INTO links_curtos_acessos'):
            self.acessos.append(dict(zip(('codigo', 'link_id', 'ip', 'ua', 'robo'), params)))
            return len(self.acessos)
        if sql.startswith('UPDATE links_curtos SET cliques_humanos'):
            link = self.links[params[0]]
            link['cliques_humanos'] += 1
            link['primeiro_clique_em'] = link['primeiro_clique_em'] or 'agora'
            return None
        if sql.startswith('INSERT INTO sms_envios'):
            i = next(self._ids)
            campos = ('produto_id', 'origem', 'etapa', 'ref_tipo', 'ref_id', 'telefone', 'texto', 'partes', 'link_id',
                      'status', 'erro')
            self.envios[i] = {'id': i, **dict(zip(campos, params)), 'provedor_id': None, 'enviado_em': None,
                              'entregue_em': None}
            return i
        if sql.startswith("UPDATE sms_envios SET status = 'enviando'"):
            envio = self.envios.get(params[0])
            if envio and envio['status'] == 'pendente':
                envio['status'] = 'enviando'
                return 1
            return 0
        if sql.startswith('SELECT * FROM sms_envios WHERE id'):
            return dict(self.envios[params[0]])
        if sql.startswith('SELECT id FROM sms_envios WHERE id'):
            return {'id': params[0]} if params[0] in self.envios else None
        if sql.startswith('SELECT id FROM sms_envios WHERE telefone'):
            achados = [e for e in self.envios.values() if e['telefone'] == params[0] and e['status'] == 'enviado']
            return {'id': achados[0]['id']} if achados else None
        if sql.startswith('SELECT 1 FROM sms_envios WHERE telefone'):
            ativos = ('pendente', 'enviando', 'enviado', 'entregue')
            achados = [e for e in self.envios.values() if e['telefone'] == params[0] and e['status'] in ativos]
            return {'1': 1} if achados else None   # o relógio dos testes: todo envio gravado é "recente"
        if sql.startswith('UPDATE sms_envios SET'):
            envio = self.envios[params[-1]]
            novo = re.search(r"status = '(\w+)'", sql).group(1)
            if "AND status = 'pendente'" in sql and envio['status'] != 'pendente':
                return 0
            if "AND status <> 'entregue'" in sql and envio['status'] == 'entregue':
                return 0
            envio['status'] = novo
            if 'provedor_id' in sql:
                envio['provedor_id'] = params[0]
            elif 'erro = %s' in sql:
                envio['erro'] = params[0]
            return 1
        raise AssertionError(f'SQL não previsto no banco falso: {sql}')


@pytest.fixture
def banco(monkeypatch):
    import types
    falso = BancoFalso()
    monkeypatch.setitem(sys.modules, 'database', types.SimpleNamespace(db=falso))
    return falso
