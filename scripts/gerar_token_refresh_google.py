from google_auth_oauthlib.flow import InstalledAppFlow

# As credenciais que você gerou no Google Cloud Console
# google-ads.yaml é recomendado para uso em produção, mas para gerar o refresh token você pode usar esse script simples, preenchendo com seu client_id e client_secret, e rodando localmente. O fluxo de autenticação vai abrir uma janela do navegador para você fazer login com a conta Google que tem acesso ao Google Ads, e depois vai imprimir o refresh token no console.
client_id = "CLIENT_ID_GOOGLE_CLOUD"
client_secret = "CLIENT_SECRET_GOOGLE_CLOUD"
scopes = ["https://www.googleapis.com/auth/adwords"]

flow = InstalledAppFlow.from_client_config(
    {"installed": {"client_id": client_id, "client_secret": client_secret,
                   "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                   "token_uri": "https://oauth2.googleapis.com/token"}},
    scopes=scopes
)

credentials = flow.run_local_server(port=0)
print(f"\nSeu Refresh Token é: {credentials.refresh_token}")
