#!/usr/bin/env bash
# PreToolUse (Bash): no ambiente de DEV, bloqueia comandos que chamem a API oficial da Meta.
# DEV é detectado pelo marcador WHATSAPP_API_URL=http://127.0.0.1:9/ no .env — em produção o
# .env aponta pra URL real e este hook não bloqueia nada.
set -euo pipefail

cmd=$(jq -r '.tool_input.command // empty')
env_file="${CLAUDE_PROJECT_DIR:-.}/.env"

grep -qE '^WHATSAPP_API_URL=https?://127\.0\.0\.1:9/?' "$env_file" 2>/dev/null || exit 0
grep -qiE 'graph\.facebook\.com|graph\.whatsapp\.com' <<<"$cmd" || exit 0
# Só bloqueia quando há um cliente HTTP no comando — grep/leitura de código que cita o domínio passa
grep -qiE '(^|[^a-z])(curl|wget|http|httpx|requests|urllib|aiohttp)([^a-z]|$)' <<<"$cmd" || exit 0

jq -n '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "deny",
    permissionDecisionReason: "Bloqueado pelo hook do projeto: o dev local nunca chama a API oficial da Meta (graph.facebook.com). Para testar envio, use o chip do gateway (WPP_WEB_API_URL)."
  }
}'
