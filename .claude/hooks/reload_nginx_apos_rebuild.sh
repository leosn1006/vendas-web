#!/usr/bin/env bash
# PostToolUse (Bash): depois de recriar/reiniciar app, worker-* ou beat via docker compose,
# roda `make reload-nginx` — o container volta com IP novo e o nginx, com o IP antigo em cache,
# responde 502 até ser recarregado.
set -uo pipefail

cmd=$(jq -r '.tool_input.command // empty')

# Só `docker compose up` / `restart` (build sozinho não recria container)
grep -qE 'docker[ -]compose[^|;&]*[[:space:]](up|restart)([[:space:]]|$)' <<<"$cmd" || exit 0

# Serviço afetado: app/worker/beat citado, ou nenhum serviço citado (sobe tudo)
if ! grep -qE '(^|[[:space:]])(app|worker-[a-z]+|beat)([[:space:]]|$)' <<<"$cmd"; then
  grep -qE '(^|[[:space:]])(nginx|db|redis|flower|certbot)([[:space:]]|$)' <<<"$cmd" && exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

# Nginx fora do ar: não há o que recarregar
if ! docker compose ps --status running --services 2>/dev/null | grep -qx nginx; then
  exit 0
fi

if out=$(make reload-nginx 2>&1); then
  msg="Hook: nginx recarregado automaticamente após o rebuild (make reload-nginx OK)."
else
  msg="Hook: FALHOU o make reload-nginx após o rebuild — risco de 502. Saída: ${out}"
fi

jq -n --arg m "$msg" '{
  systemMessage: $m,
  hookSpecificOutput: { hookEventName: "PostToolUse", additionalContext: $m }
}'
