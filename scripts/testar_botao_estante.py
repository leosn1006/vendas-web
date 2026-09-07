#!/usr/bin/env python3
"""
Teste manual e isolado do botão de link da Estante (mensagem interactive/cta_url).

Cria (ou reaproveita) um pedido de teste do produto Temperos (id 11) no
telefone 556182487487 (api_phone_number_id=1134906636380677,
token_env_key=WHATSAPP_ACCESS_TOKEN_LC -> domínio lclivros.com.br) e envia
o botão de link diretamente para o número pessoal informado, usando as
mesmas funções reais (montar_link_estante / enviar_botao_link) que o
executor de fluxo dinâmico vai usar depois. Não passa por
acoes_fluxo_produto nem por fluxo_pedido_dinamico — é só para validar
visualmente como a mensagem chega no celular.

Uso:
    python scripts/testar_botao_estante.py
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv()

if os.getenv('DB_HOST') == 'db':
    os.environ['DB_HOST'] = 'localhost'

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from database import criar_pedido, get_pedido, get_ultimo_pedido_by_phone
from whatsapp import montar_link_estante, enviar_botao_link
from fluxos._executor_acao import substituir_variaveis

PRODUTO_ID = 11  # Temperos Caseiros no Pote
PHONE_NUMBER_ID = '1134906636380677'  # telefone 556182487487, token_env_key=WHATSAPP_ACCESS_TOKEN_LC
CONTACT_PHONE = '5561981163324'  # número pessoal de teste (janela de 24h já aberta)

TEXTO_MENSAGEM = (
    "@nome_cliente, seu acesso já está disponível! Clique no botão abaixo para entrar na plataforma 👇"
)
TEXTO_BOTAO = "Ver produto"


def main():
    pedido = get_ultimo_pedido_by_phone(CONTACT_PHONE, PRODUTO_ID, PHONE_NUMBER_ID)

    if pedido is None:
        pedido_id = criar_pedido({
            'produto_id': PRODUTO_ID,
            'valor_pago': 0.0,
            'phone_number_id': PHONE_NUMBER_ID,
            'contact_phone': CONTACT_PHONE,
            'contact_to': CONTACT_PHONE,
            'contact_name': 'Teste Botão Estante',
            'bsuid': None,
            'mensagem_sugerida': 'teste botão estante',
        })
        pedido = get_pedido(pedido_id)
        print(f"Pedido de teste criado: #{pedido_id}")
    else:
        print(f"Reaproveitando pedido de teste existente: #{pedido['id']}")

    link = montar_link_estante(pedido)
    print(f"Link da Estante: {link}")

    texto = substituir_variaveis(TEXTO_MENSAGEM, pedido)
    print(f"contact_name='{pedido.get('contact_name')}' -> texto final: {texto}")

    message_id = enviar_botao_link(pedido, texto, link, TEXTO_BOTAO)
    print(f"Mensagem enviada! ID: {message_id}")


if __name__ == '__main__':
    main()
