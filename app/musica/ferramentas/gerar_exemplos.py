"""Gera as músicas de exemplo da landing de um idioma ("Para cada momento importante") com o fluxo de verdade: um
quiz fictício → a IA da letra (as instruções do idioma) → o gerador (o estilos.json do idioma). Custa crédito: uma
letra na OpenAI e ~11 créditos da Apiframe por exemplo.

Uso (no container, com MUSICA_GERADOR=apiframe, APIFRAME_API_KEY e OPENAI_API_KEY no .env):
    docker compose run --rm app python -m musica.ferramentas.gerar_exemplos --idioma es-MX
    docker compose run --rm app python -m musica.ferramentas.gerar_exemplos --idioma es-MX --so mama,xv

Grava em storage/musica/exemplos/<idioma>/: <slug>.mp3 (trecho de 40 s, como os do Brasil) da VERSÃO escolhida
(--versao, padrão 2), <slug>-completa.mp3 e exemplos.json (título, letra, estilo enviado). NÃO mexe no site: depois
de ouvir, copie para app/musica/static/exemplos/<idioma>/ e liste em textos.json → landing.exemplos.
"""
import argparse
import json
import sys
import time

from musica import config, idiomas
from musica.adaptadores.audio_ffmpeg import AudioFfmpeg
from musica.adaptadores.letra_openai import LetraOpenAI
from musica.dominio import quiz as _quiz
from musica.dominio import regras
from musica.dominio.modelos import GERACAO_ANDAMENTO, GERACAO_PRONTA
from musica.fabrica import criar_gerador

SEGUNDOS = 40   # como os exemplos do Brasil
ESPERA_MAXIMA = 10 * 60

# Histórias fictícias, com detalhes do México (comida, lugares, costumes), para a letra ter a cara de um pedido real.
# "pagina": a ocasião do quiz (o card leva ao quiz com ela); "nome": o rótulo do card; "img": foto que já existe.
EXEMPLOS = {
    'es-MX': [
        {'slug': 'mama-lupita', 'nome': '10 de mayo', 'img': 'mae-filha.jpg', 'respostas': {
            'para_quem': 'Mamá', 'nome': 'Guadalupe', 'apelido': 'Lupita', 'ocasiao': '10 de mayo (Día de las Madres)',
            'lembrancas': 'Un recuerdo especial con ella: los domingos hacía pozole y toda la familia llegaba a su casa\n'
                          'Una costumbre, manía o frase muy suya: siempre pregunta "¿ya comiste, mijita?" y nos persigna antes de salir\n'
                          'Lo que le quieres agradecer o decir: gracias por sacarnos adelante a mis tres hermanos y a mí, cosiendo de noche',
            'frase_obrigatoria': '', 'clima': 'emocionante', 'estilo': 'mariachi', 'voz': 'masculina', 'de': 'Ricardo'}},
        {'slug': 'abuelito-chuy', 'nome': 'Cumpleaños', 'img': 'avo-aniversario.jpg', 'respostas': {
            'para_quem': 'Abuelito', 'nome': 'Jesús', 'apelido': 'Chuy', 'ocasiao': 'Cumpleaños',
            'lembrancas': 'Un recuerdo especial con él: me enseñó a manejar en su troca vieja por los caminos del rancho en Sinaloa\n'
                          'Una costumbre, manía o frase muy suya: canta corridos mientras riega sus plantas y dice "despacito y buena letra"\n'
                          'Lo que le quieres agradecer o decir: que cumple ochenta años y sigue siendo el más fuerte de la familia',
            'frase_obrigatoria': '', 'clima': 'animada', 'estilo': 'norteno', 'voz': 'masculina', 'de': 'Daniela'}},
        {'slug': 'novia-fer', 'nome': '14 de febrero', 'img': 'casal.jpg', 'respostas': {
            'para_quem': 'Novia', 'nome': 'Fernanda', 'apelido': 'Fer', 'ocasiao': '14 de febrero (Amor y Amistad)',
            'lembrancas': 'Cómo se conocieron o un momento que los marcó: nos conocimos en una kermés de la parroquia y le gané un peluche en los dardos\n'
                          'Una manía o costumbre suya que te encanta: se ríe tan fuerte que todo el cine voltea\n'
                          'Lo que quieres que ella sienta al escuchar la canción: que no me imagino la vida sin ella',
            'frase_obrigatoria': '', 'clima': 'romantica', 'estilo': 'banda', 'voz': 'masculina', 'de': 'Alejandro'}},
        {'slug': 'papa-tono', 'nome': 'Día del Padre', 'img': 'pai-filha.jpg', 'respostas': {
            'para_quem': 'Papá', 'nome': 'Antonio', 'apelido': 'Toño', 'ocasiao': 'Día del Padre',
            'lembrancas': 'Un recuerdo especial con él: me llevaba en hombros a ver los cohetes en las fiestas del pueblo\n'
                          'Una costumbre, manía o frase muy suya: pone sus casetes de grupera los sábados mientras lava el carro\n'
                          'Lo que le quieres agradecer o decir: gracias por nunca faltar, aunque llegara cansado del trabajo',
            'frase_obrigatoria': '', 'clima': 'emocionante', 'estilo': 'grupera', 'voz': 'masculina', 'de': 'Mariana'}},
        {'slug': 'boda-ana-luis', 'nome': 'Boda', 'img': 'casamento.jpg', 'respostas': {
            'para_quem': 'Esposo', 'nome': 'Luis', 'apelido': '', 'ocasiao': 'Boda',
            'lembrancas': 'Cómo se conocieron o un momento que los marcó: nos conocimos en la prepa y él me esperaba a la salida con un elote\n'
                          'Una manía o costumbre suya que te encanta: me deja notitas en el espejo del baño\n'
                          'Lo que quieres que él sienta al escuchar la canción: que lo elegiría mil veces',
            'frase_obrigatoria': 'contigo hasta viejitos', 'clima': 'romantica', 'estilo': 'balada', 'voz': 'femenina',
            'de': 'Ana'}},
        {'slug': 'xv-sofi', 'nome': 'XV años', 'img': 'quinze-anos.jpg', 'respostas': {
            'para_quem': 'Hija', 'nome': 'Sofía', 'apelido': 'Sofi', 'ocasiao': 'XV años',
            'lembrancas': 'Un recuerdo especial con ella: de chiquita bailaba en la sala con mis zapatos de tacón\n'
                          'Una costumbre, manía o frase muy suya: siempre dice "yo puedo sola"\n'
                          'Lo que le quieres agradecer o decir: que aunque crezca siempre va a ser mi niña',
            'frase_obrigatoria': '', 'clima': 'emocionante', 'estilo': 'vals', 'voz': 'femenina', 'de': 'Mamá'}},
        {'slug': 'graduacion-dani', 'nome': 'Graduación', 'img': 'formatura.jpg', 'respostas': {
            'para_quem': 'Hijo', 'nome': 'Daniel', 'apelido': 'Dani', 'ocasiao': 'Graduación',
            'lembrancas': 'Un recuerdo especial con él: estudiaba en la mesa de la cocina hasta la madrugada con su café de olla\n'
                          'Una costumbre, manía o frase muy suya: dice "ahorita lo hago" y siempre lo termina\n'
                          'Lo que le quieres agradecer o decir: que es el primer ingeniero de la familia y estamos orgullosos',
            'frase_obrigatoria': '', 'clima': 'inspiradora', 'estilo': 'pop', 'voz': 'femenina', 'de': 'Tu familia'}},
        {'slug': 'abuelita-carmen', 'nome': 'En memoria', 'img': 'ouvindo.jpg', 'respostas': {
            'para_quem': 'Abuelita', 'nome': 'Carmen', 'apelido': '', 'ocasiao': 'En memoria de quien ya partió',
            'lembrancas': 'Un recuerdo especial con ella: nos hacía tamales en Navidad y nos dejaba ayudar a envolverlos\n'
                          'Una costumbre, manía o frase muy suya: tarareaba boleros mientras bordaba servilletas\n'
                          'Lo que le quieres agradecer o decir: que la extrañamos y que sus nietos la seguimos queriendo',
            'frase_obrigatoria': '', 'clima': 'reflexiva', 'estilo': 'bolero', 'voz': 'trio', 'de': 'Sus nietos'}},
    ],
}


def gerar(exemplo, idioma, escritor, gerador, audio, pasta, versao):
    slug, respostas = exemplo['slug'], dict(exemplo['respostas'])
    quiz = _quiz.do_idioma(idioma)
    erro = quiz.combinacao_invalida(respostas)
    if erro:
        print(f'[{slug}] resposta que o quiz não aceita: {erro}', flush=True)
        return None
    letra = escritor.escrever(idiomas.instrucoes_letra(idioma), respostas, idioma=idioma)
    print(f'[{slug}] letra: "{letra.titulo}"', flush=True)
    pedido = regras.montar_geracao(respostas, letra.titulo, letra.letra_suno, idiomas.estilos(idioma), quiz)
    job = gerador.criar(pedido, None)
    inicio = time.time()
    while time.time() - inicio < ESPERA_MAXIMA:
        time.sleep(10)
        resultado = gerador.consultar(job)
        if resultado.status == GERACAO_ANDAMENTO:
            continue
        if resultado.status != GERACAO_PRONTA or len(resultado.faixas) < versao:
            print(f'[{slug}] FALHOU: {resultado.erro}', flush=True)
            return None
        faixa = resultado.faixas[versao - 1]
        completa = pasta / f'{slug}-completa.mp3'
        audio.baixar(faixa.url, completa)
        audio.cortar_previa(completa, pasta / f'{slug}.mp3', regras.inicio_previa(faixa.duracao, SEGUNDOS), SEGUNDOS)
        print(f'[{slug}] pronto em {int(time.time() - inicio)} s (versão {versao})', flush=True)
        return {'slug': slug, 'nome': exemplo['nome'], 'img': exemplo['img'], 'quiz': respostas['ocasiao'],
                'titulo': letra.titulo, 'letra': letra.letra_exibicao, 'estilo': pedido.estilo,
                'negativo': pedido.negativo, 'observacao': letra.observacao, 'versao': versao}
    print(f'[{slug}] desisti depois de {ESPERA_MAXIMA // 60} min (job {job})', flush=True)
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--idioma', required=True, choices=sorted(EXEMPLOS))
    parser.add_argument('--so', help='só estes slugs, separados por vírgula (refazer um que não ficou bom)')
    parser.add_argument('--versao', type=int, default=2, choices=(1, 2), help='qual das 2 versões guardar (padrão 2)')
    args = parser.parse_args()
    exemplos = EXEMPLOS[args.idioma]
    if args.so:
        pedidos = {s.strip() for s in args.so.split(',')}
        exemplos = [e for e in exemplos if e['slug'] in pedidos]
    if config.GERADOR != 'apiframe' or config.LETRA_SIMULADA:
        sys.exit('Os exemplos precisam do gerador e da IA de verdade (MUSICA_GERADOR=apiframe, MUSICA_LETRA_SIMULADA=0).')
    pasta = config.PASTA_ARQUIVOS / 'exemplos' / args.idioma
    pasta.mkdir(parents=True, exist_ok=True)
    escritor = LetraOpenAI(config.MODELO_LETRA, config.ESFORCO_LETRA)
    gerador, audio = criar_gerador('apiframe'), AudioFfmpeg()
    print(f'Gerando {len(exemplos)} exemplo(s) em {args.idioma}: ~{11 * len(exemplos)} créditos da Apiframe.', flush=True)
    feitos = []
    for exemplo in exemplos:
        try:
            r = gerar(exemplo, args.idioma, escritor, gerador, audio, pasta, args.versao)
        except Exception as e:   # um exemplo que falha não perde os outros
            print(f"[{exemplo['slug']}] erro: {e}", flush=True)
            r = None
        if r:
            feitos.append(r)
    arquivo = pasta / 'exemplos.json'
    anteriores = json.loads(arquivo.read_text(encoding='utf-8')) if arquivo.exists() else []
    juntos = {e['slug']: e for e in anteriores} | {e['slug']: e for e in feitos}
    arquivo.write_text(json.dumps(list(juntos.values()), ensure_ascii=False, indent=2), encoding='utf-8')
    falhas = [e['slug'] for e in exemplos if e['slug'] not in {f['slug'] for f in feitos}]
    print(f'{len(feitos)} pronto(s) em {pasta}. ' + (f'Falharam: {", ".join(falhas)}' if falhas else 'Todos prontos.'),
          flush=True)


if __name__ == '__main__':
    main()
