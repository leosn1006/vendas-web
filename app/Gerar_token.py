import secrets

# Gera um token hexadecimal de 32 bytes (64 caracteres)
app_token = secrets.token_hex(32)

print(f"Seu App Token: {app_token}")
# Exemplo de saída: 'f1e4b9... (64 caracteres aleatórios)'
