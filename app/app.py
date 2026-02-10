from flask import Flask

app = Flask(__name__)

@app.get("/")
def home():
    return """"
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>50 Receitas de Pães Caseiros sem Glúten - Clique para receber no WhatsApp</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: #ffffff;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 15px;
        }
        .container {
            max-width: 450px;
            width: 100%;
            flex: 1;
        }
        .img-clicavel {
            width: 100%;
            height: auto;
            display: block;
            cursor: pointer;
        }
        .footer {
            width: 100%;
            max-width: 450px;
            padding: 20px 10px;
            text-align: center;
            border-top: 1px solid #e0e0e0;
            margin-top: 20px;
        }
        .footer p {
            color: #888;
            font-size: 12px;
            margin-bottom: 10px;
        }
        .footer-links {
            display: flex;
            flex-wrap: wrap;
            justify-content: center;
            gap: 8px;
        }
        .footer-links a {
            color: #666;
            text-decoration: none;
            font-size: 11px;
            padding: 5px 10px;
            border-radius: 4px;
            transition: all 0.3s ease;
        }
        .footer-links a:hover {
            color: #2d5016;
            background: #f5f5f5;
        }
        .footer-links span {
            color: #ccc;
            font-size: 11px;
        }
    </style>
</head>
<body>
    <div class="container">
        <img 
            id="imgClicavel" 
            src="https://s3.projetosdobruno.com/imagens/P%C3%A3es%20Caseiros.webp" 
            alt="50 Receitas de Pães sem Glúten - Clique para receber no WhatsApp" 
            class="img-clicavel"
        >
    </div>

    <footer class="footer">
        <p>© 2025 Receitas Digitais e Saúde. Todos os direitos reservados.</p>
        <div class="footer-links">
            <a href="/politica-privacidade.html">Política de Privacidade</a>
            <span>|</span>
            <a href="/termos-de-uso.html">Termos de Uso</a>
            <span>|</span>
            <a href="/contato.html">Contato</a>
            <span>|</span>
            <a href="/disclaimer.html">Disclaimer</a>
        </div>
    </footer>

    <script>
    document.getElementById('imgClicavel').addEventListener('click', function() {
        // Configuração dos WhatsApps
        const whatsappConfig = [
            {
                numero: '5561981173547',
                identificador: 'WHATSAPP 01'
            },
            {
                numero: '5561981102903',
                identificador: 'WHATSAPP 02'
            },
            {
                numero: '5561982325340',
                identificador: 'WHATSAPP 06'
            }
        ];
        
        // Escolhe aleatoriamente entre os 3 WhatsApps
        const indiceWhatsapp = Math.floor(Math.random() * whatsappConfig.length);
        const whatsappEscolhido = whatsappConfig[indiceWhatsapp];
        
        // Emojis e mensagem
        const emojiPool = ['☺️', '😃', '😊', '🌹', '🥰', '🙂']; 
        const indiceAleatorio = Math.floor(Math.random() * emojiPool.length); 
        const emojiEscolhido = emojiPool[indiceAleatorio];
        const mensagemBaseWA = 'Olá, tenho interesse nas receitas';
        const mensagemFinalWA = emojiEscolhido + ' ' + mensagemBaseWA; 
        
        // Webhook fixo para coletar GCLID
        const urlDoWebhook = 'https://webhook.projetosdobruno.com/webhook/GERALGCLID';
        
        // URL do WhatsApp escolhido
        const urlWhatsapp = 'https://wa.me/' + whatsappEscolhido.numero + '?text=' + encodeURIComponent(mensagemFinalWA);
        
        // Captura dados da página
        const urlDaPaginaAtual = window.location.href; 
        const queryString = window.location.search;
        const urlParams = new URLSearchParams(queryString);
        const gclidCode = urlParams.get('gclid');
        const timestampUnixSegundos = Math.floor(new Date().getTime() / 1000);
        
        // Dados para enviar ao webhook
        const dadosParaEnviar = {
            chave_emoji: emojiEscolhido, 
            timestamp_unix: timestampUnixSegundos, 
            gclid_isolado: gclidCode,
            url_completa: urlDaPaginaAtual,
            whatsapp: whatsappEscolhido.identificador
        };
        
        // Dispara webhook em background (fire-and-forget)
        fetch(urlDoWebhook, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dadosParaEnviar),
            keepalive: true
        });
        
        // Redireciona IMEDIATAMENTE para o WhatsApp
        window.location.href = urlWhatsapp;
    });
    </script>
</body>
</html>

"""