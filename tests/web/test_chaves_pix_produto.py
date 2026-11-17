"""Cadastro de chave PIX no admin (adicionar_chave_pix_produto): chave nova, chave desativada que volta,
chave já ativa (nada muda) e chave ativa em outro produto (recusada). Sem banco: um falso em memória."""
import re

import pytest

import database
from database import ChavePixEmOutroProduto, adicionar_chave_pix_produto


class _BancoChaves:
    """Imita só as 4 consultas de adicionar_chave_pix_produto sobre uma lista de linhas."""

    def __init__(self, linhas):
        self.linhas = linhas

    def execute_query(self, sql, params=(), fetch_one=False, **_):
        sql = re.sub(r'\s+', ' ', sql)
        if sql.startswith('SELECT id, ativo'):
            produto_id, chave = params
            return next(({'id': r['id'], 'ativo': r['ativo']} for r in self.linhas
                         if r['produto_id'] == produto_id and r['chave_pix'] == chave), None)
        if sql.startswith('SELECT produto_id'):
            chave, produto_id = params
            return next(({'produto_id': r['produto_id']} for r in self.linhas
                         if r['chave_pix'] == chave and r['ativo'] and r['produto_id'] != produto_id), None)
        if sql.startswith('UPDATE'):
            tenant, chave_id = params
            linha = next(r for r in self.linhas if r['id'] == chave_id)
            linha.update(ativo=1, tenant_slug=tenant, para_venda_web=0)
            return 1
        if sql.startswith('INSERT'):
            produto_id, chave, tenant = params
            self.linhas.append({'id': len(self.linhas) + 100, 'produto_id': produto_id, 'chave_pix': chave,
                                'ativo': 1, 'para_venda_web': 0, 'tenant_slug': tenant})
            return 1
        raise AssertionError(f'consulta inesperada: {sql}')


def _linha(id_, produto_id, ativo, tenant='lsn-livros', para_venda_web=0, chave='+5569981073809'):
    return {'id': id_, 'produto_id': produto_id, 'chave_pix': chave, 'ativo': ativo,
            'para_venda_web': para_venda_web, 'tenant_slug': tenant}


@pytest.fixture
def banco(monkeypatch):
    def _criar(*linhas):
        b = _BancoChaves([dict(r) for r in linhas])  # cópia: as asserções comparam com o original
        monkeypatch.setattr(database, 'db', b)
        return b
    return _criar


def test_chave_nova_e_inserida(banco):
    b = banco()
    assert adicionar_chave_pix_produto(10, ' +5569981073809 ', 'lbe-livros') == 'adicionada'
    assert b.linhas == [_linha(100, 10, 1, 'lbe-livros')]


def test_chave_desativada_volta_ativa_com_a_conta_escolhida_e_sem_qr_web(banco):
    b = banco(_linha(14, 10, 0, 'lsn-livros', para_venda_web=1))
    assert adicionar_chave_pix_produto(10, '+5569981073809', 'lbe-livros') == 'reativada'
    assert b.linhas == [_linha(14, 10, 1, 'lbe-livros', para_venda_web=0)]


def test_chave_ja_ativa_nao_muda_a_conta_bb(banco):
    b = banco(_linha(14, 10, 1, 'lbe-livros', para_venda_web=1))
    assert adicionar_chave_pix_produto(10, '+5569981073809', 'lsn-livros') == 'ja_ativa'
    assert b.linhas == [_linha(14, 10, 1, 'lbe-livros', para_venda_web=1)]


@pytest.mark.parametrize('ja_existia_aqui', [False, True])
def test_chave_ativa_em_outro_produto_e_recusada(banco, ja_existia_aqui):
    linhas = [_linha(20, 12, 1)] + ([_linha(14, 10, 0)] if ja_existia_aqui else [])
    b = banco(*linhas)
    with pytest.raises(ChavePixEmOutroProduto, match='#12'):
        adicionar_chave_pix_produto(10, '+5569981073809', 'lsn-livros')
    assert b.linhas == linhas
