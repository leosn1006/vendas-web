.PHONY: help upload-google-ads-now logs-worker logs-files restart-worker

help:
	@echo "Comandos disponíveis:"
	@echo "  make upload-google-ads-now  # Dispara agora o upload de conversões Google Ads"
	@echo "  make logs-worker            # Acompanha logs do worker"
	@echo "  make logs-files             # Lista arquivos de logs rotacionados"
	@echo "  make restart-worker         # Reinicia apenas o container worker"

upload-google-ads-now:
	@echo "Disparando task tasks.processar_uploads_google_ads..."
	docker compose exec worker celery -A celery_app call tasks.processar_uploads_google_ads

logs-worker:
	docker compose logs -f worker

logs-files:
	docker compose exec worker ls -lah /app/storage/logs

restart-worker:
	docker compose restart worker

restart-nginx:
	docker compose restart nginx
