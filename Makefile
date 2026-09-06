.PHONY: help upload-google-ads-now upload-google-sheets-now buscar-pix buscar-pix-periodo orcamento-sheets-now exportar-mensagens exportar-telefones-google-ads logs-worker logs-worker-normal logs-worker-baixa logs-files restart-worker restart-nginx reload-nginx atualizar-senha criar-usuario

help:
	@echo "Comandos disponíveis:"
	@echo "  make upload-google-ads-now        # Dispara agora o upload de conversões Google Ads"
	@echo "  make upload-google-sheets-now          # Dispara agora a exportação de GCLIDs para Google Sheets"
	@echo "  make orcamento-sheets-now              # Processa orçamento de ontem via Google Sheets"
	@echo "  make orcamento-sheets-now data=2026-06-01  # Reprocessa uma data específica (yyyy-mm-dd)"
	@echo "  make buscar-pix                        # Busca PIX de hoje (conta lsn-livros) e persiste no banco"
	@echo "  make buscar-pix data=31/03/2026   # Busca PIX de uma data específica (dd/mm/yyyy)"
	@echo "  make buscar-pix data=31/03/2026 tenant=lbe-livros  # Idem, para a conta lbe-livros"
	@echo "  make buscar-pix-periodo inicio=01/03/2026 fim=31/03/2026  # Busca PIX+devoluções dia a dia num período (backfill)"
	@echo "  make buscar-pix-periodo inicio=01/03/2026 fim=31/03/2026 tenant=lbe-livros  # Idem, para a conta lbe-livros"
	@echo "  make exportar-mensagens produto=9 dias=30  # Exporta mensagens do produto (default: últimos 15 dias)"
	@echo "  make exportar-telefones-google-ads valor=10  # Exporta telefones de pedidos pagos para Google Sheets (default: valor > 10)"
	@echo "  make logs-worker                  # Acompanha logs do worker-urgente"
	@echo "  make logs-worker-normal           # Acompanha logs do worker-normal"
	@echo "  make logs-worker-baixa            # Acompanha logs do worker-baixa"
	@echo "  make logs-files                   # Lista arquivos de logs rotacionados"
	@echo "  make restart-worker               # Reinicia os três workers"
	@echo "  make restart-nginx                # Reinicia apenas o container nginx (derruba tudo se a config estiver quebrada)"
	@echo "  make reload-nginx                 # Testa e recarrega a config do nginx sem derrubar o container (use isso, não restart-nginx, ao mexer em default.conf)"
	@echo "  make atualizar-senha email=x senha=y  # Atualiza senha de um usuário admin"
	@echo "  make criar-usuario email=x senha=y nome=z perfil=admin  # Cria novo usuário"

upload-google-ads-now:
	@echo "Disparando task tasks.processar_uploads_google_ads..."
	docker compose exec worker-baixa celery -A celery_app call tasks.processar_uploads_google_ads

upload-google-sheets-now:
	@echo "Disparando task tasks.processar_uploads_google_sheets..."
	docker compose exec worker-baixa celery -A celery_app call tasks.processar_uploads_google_sheets

orcamento-sheets-now:
	@echo "Processando orçamento sheets de $(if $(data),$(data),ontem)..."
	@docker compose exec worker-baixa python -c "\
from fluxos.fluxo_orcamento_sheets import processar_orcamento_sheets; \
processar_orcamento_sheets($(if $(data),'$(data)',None))"

buscar-pix:
	@echo "Buscando PIX de $(if $(data),$(data),hoje) (conta $(if $(tenant),$(tenant),lsn-livros))..."
	@docker compose exec worker-baixa python -c "\
from fluxos.fluxo_pix_bb import executar; \
executar($(if $(data),'$(data)',None), tenant_slug='$(if $(tenant),$(tenant),lsn-livros)')"

buscar-pix-periodo:
	@echo "Buscando PIX+devoluções de $(inicio) até $(fim) (conta $(if $(tenant),$(tenant),lsn-livros))..."
	@docker compose exec worker-baixa python -c "\
import logging; logging.basicConfig(level=logging.INFO, format='%(message)s'); \
from fluxos.fluxo_pix_bb import executar_periodo; \
executar_periodo('$(inicio)', '$(fim)', tenant_slug='$(if $(tenant),$(tenant),lsn-livros)')"

exportar-mensagens:
	@echo "Exportando mensagens do produto $(produto) (últimos $(if $(dias),$(dias),15) dias)..."
	python3 scripts/exportar_mensagens_produto.py --produto-id $(produto) --dias $(if $(dias),$(dias),15)

exportar-telefones-google-ads:
	@echo "Exportando telefones de pedidos pagos (valor > $(if $(valor),$(valor),10)) para Google Sheets..."
	python3 scripts/exportar_telefones_google_ads.py --valor-minimo $(if $(valor),$(valor),10)

logs-worker:
	docker compose logs -f worker-urgente

logs-worker-normal:
	docker compose logs -f worker-normal

logs-worker-baixa:
	docker compose logs -f worker-baixa

logs-files:
	docker compose exec worker-urgente ls -lah /app/storage/logs

restart-worker:
	docker compose restart worker-urgente worker-normal worker-baixa

restart-nginx:
	docker compose restart nginx

reload-nginx:
	docker compose exec nginx nginx -t
	docker compose exec nginx nginx -s reload

atualizar-senha:
	@echo "Atualizando senha para $(email)..."
	@docker compose exec app python -c "\
from werkzeug.security import generate_password_hash; \
from database import db; \
h = generate_password_hash('$(senha)'); \
db.execute_query('UPDATE usuarios SET senha = %s WHERE email = %s', (h, '$(email)')); \
print('Senha atualizada com sucesso!')"

criar-usuario:
	@echo "Criando usuário $(email)..."
	@docker compose exec app python -c "\
from werkzeug.security import generate_password_hash; \
from database import db; \
h = generate_password_hash('$(senha)'); \
db.execute_query('INSERT INTO usuarios (email, senha, nome, perfil) VALUES (%s, %s, %s, %s)', \
('$(email)', h, '$(nome)', '$(perfil)')); \
print('Usuario criado com sucesso!')"
