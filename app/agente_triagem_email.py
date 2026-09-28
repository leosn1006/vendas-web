"""
Triagem dos e-mails que chegam na caixa de atendimento (fluxos/fluxo_email_conversas.py):
vendas x administrativo x ruído, e a categoria do pedido de ajuda. Não responde nada — só decide
o caminho (resposta pronta, fila humana ou sem ação).

Categorias vêm da análise da caixa (mar–set/2026, 94 clientes). Público: mulheres 35+, que
escrevem pouco, sem assunto, às vezes só o próprio e-mail ou a chave PIX.
"""

import logging
from typing import Literal

from pydantic import BaseModel, Field
from openai import OpenAI

logger = logging.getLogger(__name__)

client = OpenAI()

Categoria = Literal[
    'chave_pix', 'acesso_estante', 'pagou_e_cobrado', 'pagamento', 'reclamacao',
    'quer_comprar', 'duvida_uso', 'agradecimento', 'administrativo', 'ruido', 'outros',
]


class TriagemEmail(BaseModel):
    tipo: Literal['vendas', 'administrativo', 'ruido'] = Field(
        description="vendas = cliente/possível cliente dos e-books; administrativo = assunto da empresa "
                    "(fornecedor, parceria, banco, contador, governo); ruido = aviso automático/marketing.")
    categoria: Categoria
    motivo: str = Field(description="Justificativa curta em português.")


SYSTEM_PROMPT = (
    "Você faz a triagem da caixa de e-mail de uma editora que vende e-books de receitas baratos "
    "(público: mulheres 35+, escrevem pouco e com erros). Vendemos pelo site (paga antes, acessa a "
    "'Estante' com os livros) e pelo WhatsApp (recebe o livro antes e paga por PIX depois). "
    "Classifique o ÚLTIMO e-mail do cliente (texto citado de e-mails anteriores já foi removido).\n\n"
    "Categorias:\n"
    "- chave_pix: e-mail vazio ou quase vazio — só um endereço de e-mail/chave PIX, 'pagamento', 'fazer o pix', "
    "'transferir pix' — a pessoa confundiu a chave PIX com e-mail. Se ela diz que NÃO consegue pagar, ou pede "
    "a chave, uma conta, boleto ou outra forma de pagar, é pagamento (não chave_pix).\n"
    "- acesso_estante: comprou/pagou e não consegue abrir, baixar, acessar ou achar os livros; "
    "'não recebi', 'não abre', 'está vazio', 'como baixo as receitas', 'manda no meu WhatsApp'.\n"
    "- pagou_e_cobrado: diz que já pagou/comprou (geralmente respondendo a um e-mail de cobrança) ou "
    "manda o comprovante perguntando como enviar.\n"
    "- pagamento: não consegue pagar, QR code não funciona, banco recusa, pede boleto/conta/outra "
    "forma, pede prazo para pagar.\n"
    "- reclamacao: quer o dinheiro de volta, ameaça denunciar, contestou no banco, está irritada.\n"
    "- quer_comprar: pede uma receita/livro, 'quero as receitas', 'como adquiro', sem ter comprado.\n"
    "- duvida_uso: dúvida sobre o conteúdo, pode imprimir, pode vender, qualidade das imagens, grupo "
    "ou contato de WhatsApp.\n"
    "- agradecimento: só agradece, confirma ou reage ('obrigada', 'ok', 'consegui', 'já recebi', "
    "'já comprei e já recebi', '🙏') — não pede nada.\n"
    "- administrativo: assunto da empresa que não é de cliente (tipo=administrativo).\n"
    "- ruido: propaganda, notificação automática, newsletter (tipo=ruido).\n"
    "- outros: cliente, mas nenhum dos casos acima.\n\n"
    "Na dúvida entre acesso_estante e pagou_e_cobrado, use acesso_estante se ela diz que não "
    "consegue abrir/receber; pagou_e_cobrado se só avisa que já pagou. Se diz que já pagou E já "
    "recebeu, é agradecimento. Reclamação tem prioridade sobre as demais quando há pedido de "
    "reembolso ou ameaça. E-mail sem nenhum texto do cliente (só a citação de um e-mail nosso) é "
    "agradecimento."
)


def triar_email(assunto: str, corpo: str, destinatario: str, qtd_anexos: int) -> TriagemEmail:
    conteudo = (
        f"Para: {destinatario or '-'}\n"
        f"Assunto: {assunto or '(sem assunto)'}\n"
        f"Anexos: {qtd_anexos}\n"
        f"Corpo:\n{(corpo or '(vazio)')[:4000]}"
    )
    try:
        completion = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": SYSTEM_PROMPT},
                      {"role": "user", "content": conteudo}],
            response_format=TriagemEmail,
            temperature=0.0,
        )
        triagem = completion.choices[0].message.parsed
        if triagem is None:  # recusa do modelo
            raise ValueError(completion.choices[0].message.refusal or 'resposta vazia')
        return triagem
    except Exception as exc:
        logger.error(f"[TRIAGEM-EMAIL] ❌ Erro na triagem ({type(exc).__name__}): {exc}")
        # Na falha, vai pra fila humana: 'outros' sem pedido nunca gera resposta pronta
        return TriagemEmail(tipo='vendas', categoria='outros',
                            motivo=f'Erro na triagem ({type(exc).__name__}) — encaminhado ao humano.')
