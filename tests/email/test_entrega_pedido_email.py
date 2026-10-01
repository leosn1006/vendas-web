"""
E-mail de entrega das vendas do site: o link enviado é o da Estante 2 (/pedido2/<guid>), a mesma
para onde o checkout redireciona depois do pagamento.
"""
import database
from fluxos import entrega_pedido_email


def test_entrega_por_email_manda_link_da_estante_2(monkeypatch):
    enviados = []
    monkeypatch.setenv('APP_BASE_URL', 'https://lsnlivros.com.br/')
    monkeypatch.setattr(database, 'get_pedido', lambda i: {
        'id': i, 'produto_id': 12, 'email': 'cliente@x.com', 'contact_name': 'Maria Silva',
        'data_envio_ebook': None})
    monkeypatch.setattr(database, 'get_produto_disponivel_web', lambda i: {'nome': 'Fatia de Bolo'})
    monkeypatch.setattr(database, 'listar_itens_pedido', lambda i: [{'nome': 'Fatia de Bolo', 'tipo': 'principal'}])
    monkeypatch.setattr(database, 'garantir_guid_pedido', lambda i: 'abc123')
    monkeypatch.setattr(database, 'marcar_ebook_enviado', lambda i: None)
    monkeypatch.setattr(database, 'definir_gmail_thread_pedido', lambda *a: None)
    monkeypatch.setattr(database, 'salvar_mensagem_email_pedido', lambda **k: None)
    monkeypatch.setattr(entrega_pedido_email, 'rotular_enviado', lambda *a: None)
    monkeypatch.setattr(entrega_pedido_email, '_enviar_gmail', lambda **k: enviados.append(k) or {'id': 'm1'})

    entrega_pedido_email.executar(7)

    html = enviados[0]['html']
    assert 'https://lsnlivros.com.br/pedido2/abc123' in html
    assert '/pedido/abc123' not in html
