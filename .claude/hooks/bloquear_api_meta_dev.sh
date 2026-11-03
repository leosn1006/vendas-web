#!/usr/bin/env bash
# PreToolUse (Bash): no ambiente de DEV, nega por padrão os comandos que chamem a API da Meta e libera só leitura e
# evento de teste. DEV é detectado pelo marcador WHATSAPP_API_URL=http://127.0.0.1:9/ no .env — em produção o
# .env aponta pra URL real e este hook não bloqueia nada.
#
# Regra do Leo (02/11/2026): no dev não pode mandar mensagem a cliente nem mexer em webhook; consultas e testes podem.
# - Sempre negado: endpoints de mensagem, registro de número e webhook do WhatsApp.
# - Liberado: curl de leitura (GET, inclusive curl -G -d) em qualquer outro endpoint.
# - Liberado: um único curl de evento de TESTE da API de Conversões, que não conta para a campanha.
# - Negado: todo o resto, inclusive outros clientes HTTP. O token tem ads_management: outra escrita altera anúncio real.
# É uma trava contra engano, não uma barreira de segurança: só enxerga o texto do comando, não o conteúdo de um script.
set -euo pipefail

cmd=$(jq -r '.tool_input.command // empty')
env_file="${CLAUDE_PROJECT_DIR:-.}/.env"

grep -qE '^WHATSAPP_API_URL=https?://127\.0\.0\.1:9/?' "$env_file" 2>/dev/null || exit 0
grep -qiE 'graph\.facebook\.com|graph\.whatsapp\.com' <<<"$cmd" || exit 0
# Só avalia quando há um cliente HTTP no comando — grep/leitura de código que cita o domínio passa
clientes='wget|http|https|httpie|httpx|xh|aria2c|requests|urllib|aiohttp|fetch|axios|python[0-9.]*|node|ruby|perl|php|nc|ncat|socat'
grep -qiE "(^|[^a-z])(curl|$clientes)([^a-z]|$)" <<<"$cmd" || exit 0

negar() {
  jq -n --arg motivo "Bloqueado pelo hook do projeto: $1" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: $motivo
    }
  }'
  exit 0
}

if grep -qiE '/messages|/register|/deregister|/request_code|/verify_code|subscribed_apps' <<<"$cmd"; then
  negar "o dev não manda mensagem a cliente nem mexe em número ou webhook do WhatsApp. Para testar envio, use o chip do gateway (WPP_WEB_API_URL)."
fi

# No dev, só o curl é liberado: nos outros clientes não dá para ler o método.
if grep -qiE "(^|[^a-z])($clientes)([^a-z]|$)" <<<"$(sed -E 's#https?://##g' <<<"$cmd")"; then
  negar "no dev, chamadas à Meta só pelo curl, em que dá para conferir o método."
fi

# O `cut -d<x>` que lê o token do .env e o `-X GET` explícito não são escrita. O valor de um cabeçalho não é opção.
limpo=$(sed -E "s/cut +-d[^ ]*//g; s/(-X|--request)[ =]*GET//g; s/(-H|--header) +\"[^\"]*\"//g; s/(-H|--header) +'[^']*'//g" <<<"$cmd")
ini='(^|[[:space:]"'"'"'=])'
# Opções que escondem o que será enviado, ou a troca de método pela URL, que a Graph API aceita.
if grep -qE "$ini"'(-[a-zA-Z]*K|--config|--next)' <<<"$limpo" || grep -qiE 'method=' <<<"$limpo"; then
  negar "o comando esconde o método ou o corpo da chamada à Meta."
fi

# Um trecho por comando do shell: o -G de um curl não vale para o outro. Corpo sem -G no mesmo trecho é escrita.
trechos=$(sed -E 's/;|&&|\|\||\||&/\n/g' <<<"$limpo")
le_e_so_le=1
if grep -qE "$ini"'(-[a-zA-Z]*[FTX]|--(request|form|upload-file|json|method|url-query-post))' <<<"$limpo"; then
  le_e_so_le=0
fi
while IFS= read -r trecho; do
  if grep -qE "$ini"'(-[a-zA-Z]*d|--data|--expand-data|--variable)' <<<"$trecho" \
     && ! { grep -qE '(^|[^a-z])curl([^a-z]|$)' <<<"$trecho" && grep -qE "$ini"'(-[a-zA-Z]*G|--get)' <<<"$trecho"; }; then
    le_e_so_le=0
  fi
done <<<"$trechos"
[ "$le_e_so_le" = "0" ] || exit 0

# Evento de teste: um único curl, para /<dataset>/events, com um só corpo à vista e o código na RAIZ do JSON (fora
# dela, a Meta contaria o evento como real).
curl_trecho=$(grep -E '(^|[^a-z])curl([^a-z]|$)' <<<"$trechos" || true)
corpo=$(sed -nE "s/.*(-d|--data|--data-raw|--json) +'([^']*)'.*/\2/p" <<<"$curl_trecho")
if [ "$(grep -oE '(^|[^a-z])curl([^a-z]|$)' <<<"$cmd" | wc -l | tr -d ' ')" = "1" ] \
   && [ "$(grep -oE "$ini"'(-d|--data[a-z-]*|--json|--form|-F)([[:space:]=]|$)' <<<"$curl_trecho" | wc -l | tr -d ' ')" = "1" ] \
   && grep -qE 'graph\.facebook\.com/v[0-9.]+/[0-9]+/events' <<<"$curl_trecho" \
   && jq -e '.test_event_code | strings | length > 0' <<<"$corpo" >/dev/null 2>&1 \
   && ! grep -qE '#|@|\$\(' <<<"$curl_trecho"; then
  exit 0
fi

negar "no dev, a escrita na Meta só é liberada para evento de teste (um curl em /<dataset>/events com test_event_code). Consultas (GET) estão liberadas."
