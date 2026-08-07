#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."

docker compose run --rm certbot renew --quiet
docker compose exec nginx nginx -t
docker compose exec nginx nginx -s reload
