"""Gera as amostras de estilo do quiz ("aperte o play para ouvir") com o gerador de verdade (custa crédito:
11 créditos da Apiframe por estilo; cada geração traz 2 versões).

Uso (no container, com MUSICA_GERADOR=apiframe e APIFRAME_API_KEY no .env):
    docker compose exec app python -m musica.ferramentas.gerar_amostras --estilos rock,gospel
    docker compose exec app python -m musica.ferramentas.gerar_amostras --todos

Grava em storage/musica/amostras/<estilo>-1.mp3 e -2.mp3 (trecho de 30 s das duas versões) — NÃO troca as amostras do
site. Depois de ouvir e escolher, copie a melhor para app/musica/static/estilos/<estilo>.mp3 e faça o deploy.
Todas usam a mesma letra neutra, o tom "emocionante" e a primeira voz do estilo, para comparar só o gênero.
"""
import argparse
import sys
import time

from musica import config
from musica.adaptadores.audio_ffmpeg import AudioFfmpeg
from musica.dominio import regras
from musica.dominio.modelos import GERACAO_ANDAMENTO, GERACAO_PRONTA
from musica.dominio.quiz import ESTILOS, vozes_para
from musica.fabrica import criar_gerador, servicos

LETRA_NEUTRA = """[Verse 1]
Hoje eu vim te agradecer
Por tudo que você me fez viver
Cada passo, cada amanhecer
Tem um pouco de você

[Chorus]
Essa canção é pra você
Pra lembrar o que é querer bem
Mesmo longe eu vou dizer
Que amor igual ninguém tem

[Verse 2]
Teu sorriso é meu lugar
Tua voz me ensina a sonhar
Se o caminho me cansar
É em você que eu vou voltar

[Chorus]
Essa canção é pra você
Pra lembrar o que é querer bem
Mesmo longe eu vou dizer
Que amor igual ninguém tem"""

SEGUNDOS = 30
ESPERA_MAXIMA = 10 * 60


def gerar(estilo, gerador, audio, tabela, pasta):
    respostas = {'estilo': estilo, 'clima': 'emocionante', 'voz': vozes_para(estilo)[0]}
    pedido = regras.montar_geracao(respostas, f'Amostra {estilo}', LETRA_NEUTRA, tabela)
    print(f'[{estilo}] style: {pedido.estilo}\n[{estilo}] negativo: {pedido.negativo}', flush=True)
    job = gerador.criar(pedido, None)
    inicio = time.time()
    while time.time() - inicio < ESPERA_MAXIMA:
        time.sleep(10)
        resultado = gerador.consultar(job)
        if resultado.status == GERACAO_ANDAMENTO:
            continue
        if resultado.status != GERACAO_PRONTA:
            print(f'[{estilo}] FALHOU: {resultado.erro}', flush=True)
            return False
        for numero, faixa in enumerate(resultado.faixas[:2], start=1):
            completa = pasta / f'{estilo}-{numero}-completa.mp3'
            audio.baixar(faixa.url, completa)
            audio.cortar_previa(completa, pasta / f'{estilo}-{numero}.mp3',
                                regras.inicio_previa(faixa.duracao, SEGUNDOS), SEGUNDOS)
            completa.unlink(missing_ok=True)
        print(f'[{estilo}] pronto em {int(time.time() - inicio)} s: {pasta}/{estilo}-1.mp3 e -2.mp3', flush=True)
        return True
    print(f'[{estilo}] desisti depois de {ESPERA_MAXIMA // 60} min (job {job})', flush=True)
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument('--estilos', help='estilos separados por vírgula (ex.: rock,gospel)')
    grupo.add_argument('--todos', action='store_true', help='todos os estilos (~11 créditos cada)')
    args = parser.parse_args()
    validos = [e for e, _ in ESTILOS]
    estilos = validos if args.todos else [e.strip() for e in args.estilos.split(',') if e.strip()]
    desconhecidos = [e for e in estilos if e not in validos]
    if desconhecidos:
        sys.exit(f'Estilos desconhecidos: {desconhecidos}. Válidos: {validos}')
    if config.GERADOR != 'apiframe':
        sys.exit(f'MUSICA_GERADOR={config.GERADOR!r}: as amostras precisam do gerador de verdade (apiframe).')
    pasta = config.PASTA_ARQUIVOS / 'amostras'
    pasta.mkdir(parents=True, exist_ok=True)
    gerador, audio, tabela = criar_gerador('apiframe'), AudioFfmpeg(), servicos().estilos
    print(f'Gerando {len(estilos)} estilo(s), ~{11 * len(estilos)} créditos da Apiframe.', flush=True)
    resultados = {e: gerar(e, gerador, audio, tabela, pasta) for e in estilos}
    falhas = [e for e, ok in resultados.items() if not ok]
    print('Falharam: ' + ', '.join(falhas) if falhas else 'Todos prontos.', flush=True)


if __name__ == '__main__':
    main()
