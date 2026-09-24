#!/usr/bin/env bash
# Confere todos os pontos de contato de um domínio no código.
# Uso: verificar_dominio.sh <dominio> <SLUG_ENV> [completo|espelho|webhook]
#   ex.: verificar_dominio.sh barreiroslivros.com.br BARREIROSLIVROS completo
# SLUG_ENV = sufixo das variáveis WHATSAPP_APP_SECRET_<SLUG_ENV> (num espelho, o da marca original).
set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 2

dom="${1:?informe o domínio}"; slug="${2:?informe o SLUG_ENV}"; tipo="${3:-completo}"
falhas=0
ok()   { printf '  ✅ %s\n' "$1"; }
erro() { printf '  ❌ %s\n' "$1"; falhas=$((falhas+1)); }
checa() { if eval "$2" >/dev/null 2>&1; then ok "$1"; else erro "$1"; fi; }

echo "== nginx (infra/nginx/conf.d/default.conf)"
n=$(grep -cE "server_name[^;]*[[:space:]]$dom[[:space:];]" infra/nginx/conf.d/default.conf)
[ "$n" -ge 1 ] && ok "server_name $dom aparece em $n bloco(s)" || erro "server_name $dom não encontrado"
checa "location do ACME challenge presente" "grep -A6 -E 'server_name[^;]* $dom[ ;]' infra/nginx/conf.d/default.conf | grep -q acme-challenge"
if grep -qE "^[^#]*ssl_certificate .*/live/$dom/" infra/nginx/conf.d/default.conf; then
  ok "bloco 443 ATIVO (só suba pro VPS depois do certbot emitir o cert)"
elif grep -qE "#.*ssl_certificate .*/live/$dom/" infra/nginx/conf.d/default.conf; then
  ok "bloco 443 comentado (aguardando certbot)"
else
  erro "bloco 443 ausente (nem ativo nem comentado)"
fi

echo "== app/app.py"
fn=$(grep -B2 -E "'$dom' in host|\"$dom\" in host|$dom" app/app.py | grep -oE "def _is_[a-z0-9_]+" | head -1 | sed 's/def //')
if [ -n "$fn" ]; then
  ok "host reconhecido em $fn()"
  usos=$(grep "$fn()" app/app.py | grep -vc "def $fn")
  case "$tipo" in
    completo) [ "$usos" -ge 5 ] && ok "$fn() usado em $usos rotas" || erro "$fn() usado em $usos rotas (esperado 5: / /portifolio /politica-privacidade /termos-de-uso /contato)";;
    webhook)  [ "$usos" -ge 2 ] && ok "$fn() usado em $usos rotas" || erro "$fn() usado em $usos rotas (esperado ≥2: / e /portifolio)";;
    espelho)  ok "espelho: reaproveita as rotas de $fn()";;
  esac
  if [ "$tipo" != espelho ]; then
    for t in $(grep -A1 "$fn()" app/app.py | grep -oE "'[a-z0-9_-]+\.html'" | tr -d "'" | sort -u); do
      checa "template $t existe" "test -f app/templates/$t"
    done
  fi
else
  erro "nenhuma função _is_*() reconhece $dom"
fi

echo "== app/whatsapp_seguranca.py"
checa "_HOST_SECRET_MAP: '$dom' -> WHATSAPP_APP_SECRET_$slug" "grep -qE \"'$dom': *'WHATSAPP_APP_SECRET_$slug'\" app/whatsapp_seguranca.py"
checa "_HOST_ACCESS_TOKEN_MAP: '$dom' -> WHATSAPP_ACCESS_TOKEN_$slug" "grep -qE \"'$dom': *'WHATSAPP_ACCESS_TOKEN_$slug'\" app/whatsapp_seguranca.py"

echo "== docker-compose.yml (app, worker-urgente, worker-normal, worker-baixa)"
for v in WHATSAPP_APP_SECRET_$slug WHATSAPP_ACCESS_TOKEN_$slug; do
  n=$(grep -cE "^ *- $v=\\\$\{$v:-\}" docker-compose.yml)
  [ "$n" -ge 4 ] && ok "$v em $n serviços" || erro "$v em $n de 4 serviços — sem isso o container não recebe a variável e a Meta leva 401"
done

echo "== .env.example"
for v in WHATSAPP_APP_SECRET_$slug WHATSAPP_ACCESS_TOKEN_$slug; do
  checa "$v documentada" "grep -q '^$v=' .env.example"
done

echo "== sintaxe"
checa "app.py e whatsapp_seguranca.py compilam" "python3 -m py_compile app/app.py app/whatsapp_seguranca.py"
checa "docker-compose.yml válido" "docker compose config -q"

echo
[ "$falhas" -eq 0 ] && echo "Tudo certo para $dom." || echo "$falhas problema(s) em $dom."
exit "$falhas"
