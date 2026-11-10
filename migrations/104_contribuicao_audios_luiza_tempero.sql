-- Áudios da Luiza gravados para a contribuição no site do Tempero (10/11/2026, docs/CONTRIBUICAO_WEB.md).
-- Os arquivos estão em static/audios/contribuicao/ (mp3, volume normalizado). As transcrições (botão "ler em vez de
-- ouvir") foram ajustadas ao que ela falou na gravação. Substitui a configuração provisória do piloto, que apontava
-- para os .ogg do WhatsApp (falam em comprovante). Idempotente.
SET NAMES utf8mb4;

UPDATE contribuicao_config SET
    audio_intro    = 'audios/contribuicao/tempero-intro-v1.mp3',
    audio_cobranca = 'audios/contribuicao/tempero-cobranca-v1.mp3',
    audio_lembrete = 'audios/contribuicao/tempero-lembrete-v1.mp3',
    texto_intro = 'Oi, meu bem, tudo bem? Eu sou a Luiza e eu trabalho com cozinha há muitos anos. E nesse tempo eu aprendi que o segredo de uma cozinha realmente gostosa está no tempero. Por isso, eu organizei um material simples e prático, com os meus melhores temperos caseiros. Tem temperos secos, pastosos, misturas prontas para o dia a dia e combinações especiais para carne, frango, arroz, feijão e muito mais. Tudo natural, saboroso e sem conservantes. Eu também ensino as proporções certinhas, como conservar e até ideias para quem quiser vender e fazer uma renda extra. E pode ficar tranquila, porque é tudo muito fácil de fazer, mesmo para quem não tem experiência nenhuma na cozinha. A maioria dos ingredientes você já deve ter até aí na sua casa.\n\nE funciona assim: o material completo custa 67 reais, mas aqui eu te mando o livro agora, você dá uma olhadinha e, se gostar, faz uma contribuição de apenas 10 reais. E depois da sua contribuição, eu libero dois bônus especiais: um com dicas de como vender temperos no pote e outro com receitas de molhos caseiros que fazem o maior sucesso por aqui. Se você quiser receber agora, é só tocar no botão aqui embaixo.',
    texto_cobranca = 'Prontinho, meu bem, o seu livro já está aqui na sua estante. É só tocar nele que ele abre direitinho. As receitas são super simples, com passo a passo detalhado. Mesmo que você nunca tenha feito isso antes, dessa vez você vai arrasar. Agora eu conto com a sua honestidade pra fazer a contribuição de 10 reais, tá? É só tocar no botão aqui embaixo, pode ser no Pix ou no cartão. Assim que cair, seus dois bônus aparecem aqui na hora. Não precisa nem mandar comprovante. Muito obrigada pela confiança!',
    texto_lembrete = 'Oi, meu bem, aqui é a Luiza de novo! Eu sei como a rotina é corrida e a gente acaba deixando algumas coisinhas pra depois. Mas quando você conseguir um tempinho pra fazer a sua contribuição de 10 reais, eu vou ficar muito agradecida. Esse valor é simbólico, mas ele realmente me ajuda a continuar criando essas receitas. E lembra: assim que ela cair, os seus bônus, as dicas de como vender temperos no pote e as receitinhas de molhos caseiros, aparecem aqui pra você na hora. Se tiver qualquer dificuldade, é só responder o e-mail que eu te ajudo, tá bom?'
WHERE produto_id = 11;

SELECT produto_id, percentual_estante, audio_intro, audio_cobranca, audio_lembrete FROM contribuicao_config;
