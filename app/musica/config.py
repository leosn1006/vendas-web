"""Configuração técnica do módulo Música (lida do .env): provedores, limites e chaves. O que é do PRODUTO fica no
banco: qual produto vende (o que tem plano de música), preços (plano e order bumps), remetente e a empresa
(configuração fiscal ligada ao produto). Ver docs/MUSICA.md."""
import os
from pathlib import Path

PASTA_MODULO = Path(__file__).resolve().parent
PASTA_CONTEUDO = PASTA_MODULO / 'conteudo'


def _int(nome, padrao):
    try:
        return int(os.getenv(nome, padrao))
    except ValueError:
        return int(padrao)


# Gerador de música (a borda que pode mudar): apiframe (MVP) | suno (conta própria, futuro) | simulado (dev/testes).
GERADOR = os.getenv('MUSICA_GERADOR', 'simulado').strip().lower()
APIFRAME_API_KEY = os.getenv('APIFRAME_API_KEY', '')
SUNO_VERSAO = os.getenv('MUSICA_SUNO_VERSAO', 'V5_5')

# Letra: a nossa integração com a OpenAI (OPENAI_API_KEY, a mesma dos agentes). Sem chave: letra simulada.
MODELO_LETRA = os.getenv('MUSICA_MODELO_LETRA', 'gpt-6.1-sol')
ESFORCO_LETRA = os.getenv('MUSICA_ESFORCO_LETRA', 'medium')   # low | medium | high (modelos com raciocínio)
LETRA_SIMULADA = os.getenv('MUSICA_LETRA_SIMULADA', '0') == '1' or not os.getenv('OPENAI_API_KEY')

# Endereço público (para o webhook do gerador e os links dos e-mails). Vazio: o host da requisição.
URL_PUBLICA = os.getenv('MUSICA_URL_PUBLICA', '').rstrip('/')

# Regras do funil.
LIMITE_PREVIAS_DIA = _int('MUSICA_LIMITE_PREVIAS_DIA', 3)       # gerações grátis por e-mail ou IP em 24 h
LIMITE_LETRAS_DIA = _int('MUSICA_LIMITE_LETRAS_DIA', 5)         # quizzes (letras na OpenAI) por e-mail ou IP em 24 h
LIMITE_AJUSTES_LETRA = _int('MUSICA_LIMITE_AJUSTES_LETRA', 2)
LIMITE_OUTRA_VERSAO = _int('MUSICA_LIMITE_OUTRA_VERSAO', 1)
PREVIA_SEGUNDOS = _int('MUSICA_PREVIA_SEGUNDOS', 40)
MAX_TENTATIVAS_GERACAO = 3      # se o gerador falhar, tenta de novo até este total
MINUTOS_PARA_TRAVA = 6          # geração que passa disso é tratada como falha (e tenta de novo)
DIAS_GUARDAR_NAO_PAGAS = 90     # promessa da política de privacidade

# Lembretes por e-mail para quem parou na letra, na prévia ou no checkout (docs/MUSICA.md "Lembretes"): minutos depois
# de entrar na etapa, horário em que podem sair (Brasília; fora dele esperam a manhã) e por quantos dias valem.
LEMBRETES_MINUTOS = (15, 180, 1440)
LEMBRETES_JANELA = (8, 22)
LEMBRETES_DIAS = 3
LEMBRETES_INTERVALO_EMAIL = 120   # minutos mínimos entre dois lembretes para o mesmo e-mail (de qualquer música)

# Presente por e-mail que não chegou (erro no envio ou devolução, quase sempre caixa lotada): até 4 envios no mesmo
# dia, esperando 1 h, 2 h e 4 h entre eles. Depois disso, quem comprou é avisado para mandar o link por conta própria.
PRESENTE_MAX_TENTATIVAS = 4
PRESENTE_ESPERAS_HORAS = (1, 2, 4)

# Videoclipe: letra como legenda (transcrição da OpenAI, uns R$ 0,10 por música). 0 desliga.
LEGENDA_VIDEO = os.getenv('MUSICA_LEGENDA_VIDEO', '1') == '1'

# Anti-robô (Cloudflare Turnstile, opcional).
TURNSTILE_SITE_KEY = os.getenv('TURNSTILE_SITE_KEY', '')
TURNSTILE_SECRET = os.getenv('TURNSTILE_SECRET', '')

# WhatsApp: preparado, desligado até haver número para o produto.
WHATSAPP_ATIVO = os.getenv('MUSICA_WHATSAPP_ATIVO', '0') == '1'

# Custo estimado por geração/letra (centavos), para o ROI do produto.
CUSTO_GERACAO_CENTAVOS = _int('MUSICA_CUSTO_GERACAO_CENTAVOS', 60)
CUSTO_LETRA_CENTAVOS = _int('MUSICA_CUSTO_LETRA_CENTAVOS', 25)

# Arquivos (privados; o volume ./storage é compartilhado entre o app e os workers).
PASTA_ARQUIVOS = Path(os.getenv('MUSICA_PASTA_ARQUIVOS', PASTA_MODULO.parent / 'storage' / 'musica'))
