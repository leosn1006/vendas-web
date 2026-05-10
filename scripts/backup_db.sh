#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="$PROJECT_DIR/backups"
DATE=$(date +%Y%m%d_%H%M%S)
FILENAME="vendasdb_${DATE}.sql.gz"
RETAIN_DAYS=7

# Carrega variáveis do .env (apenas linhas CHAVE=VALOR, ignora comentários e linhas soltas)
set -a
source <(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$PROJECT_DIR/.env")
set +a

mkdir -p "$BACKUP_DIR"

# Limpa arquivo parcial caso o script aborte no meio do dump
trap 'rm -f "$BACKUP_DIR/$FILENAME"' ERR

MYSQL_PWD="$DB_PASSWORD" docker compose -f "$PROJECT_DIR/docker-compose.yml" exec -T db \
  mysqldump \
  -u"$DB_USER" \
  --single-transaction \
  --routines \
  "$DB_NAME" \
  | gzip > "$BACKUP_DIR/$FILENAME"

[ -s "$BACKUP_DIR/$FILENAME" ] || { echo "ERRO: dump vazio — verifique permissões do usuário $DB_USER"; rm -f "$BACKUP_DIR/$FILENAME"; exit 1; }

# Remove backups mais antigos que RETAIN_DAYS dias
find "$BACKUP_DIR" -name "vendasdb_*.sql.gz" -mtime +"$RETAIN_DAYS" -delete

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Backup OK: $FILENAME ($(du -sh "$BACKUP_DIR/$FILENAME" | cut -f1))"
