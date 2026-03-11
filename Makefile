.PHONY: help upload-google-ads-now upload-google-sheets-now logs-worker logs-files restart-worker restart-nginx atualizar-senha criar-usuario

help:
	@echo "Comandos disponíveis:"
	@echo "  make upload-google-ads-now        # Dispara agora o upload de conversões Google Ads"
	@echo "  make upload-google-sheets-now     # Dispara agora a exportação de GCLIDs para Google Sheets"
	@echo "  make logs-worker                  # Acompanha logs do worker"
	@echo "  make logs-files                   # Lista arquivos de logs rotacionados"
	@echo "  make restart-worker               # Reinicia apenas o container worker"
	@echo "  make restart-nginx                # Reinicia apenas o container nginx"
	@echo "  make atualizar-senha email=x senha=y  # Atualiza senha de um usuário admin"
	@echo "  make criar-usuario email=x senha=y nome=z perfil=admin  # Cria novo usuário"

upload-google-ads-now:
	@echo "Disparando task tasks.processar_uploads_google_ads..."
	docker compose exec worker celery -A celery_app call tasks.processar_uploads_google_ads

upload-google-sheets-now:
	@echo "Disparando task tasks.processar_uploads_google_sheets..."
	docker compose exec worker celery -A celery_app call tasks.processar_uploads_google_sheets

logs-worker:
	docker compose logs -f worker

logs-files:
	docker compose exec worker ls -lah /app/storage/logs

restart-worker:
	docker compose restart worker

restart-nginx:
	docker compose restart nginx

atualizar-senha:
	@echo "Atualizando senha para $(email)..."
	@docker compose exec app python -c "\
from werkzeug.security import generate_password_hash; \
from database import db; \
h = generate_password_hash('$(senha)'); \
db.execute_query('UPDATE usuarios SET senha = %s WHERE email = %s', (h, '$(email)')); \
print('✅ Senha atualizada com sucesso!')"

criar-usuario:
	@echo "Criando usuário $(email)..."
	@docker compose exec app python -c "\
from werkzeug.security import generate_password_hash; \
from database import db; \
h = generate_password_hash('$(senha)'); \
db.execute_query('INSERT INTO usuarios (email, senha, nome, perfil) VALUES (%s, %s, %s, %s)', \
('$(email)', h, '$(nome)', '$(perfil)')); \
print('✅ Usuário criado com sucesso!')"
