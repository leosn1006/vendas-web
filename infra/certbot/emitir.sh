#!/usr/bin/env bash
# Emite certificado Let's Encrypt (HTTP-01) para um ou mais domínios, um
# certificado por domínio, em /etc/letsencrypt/live/<dominio>/ (o caminho que o
# bloco 443 do nginx usa). Segue para o próximo se um falhar e mostra o resumo
# no fim. Rodar na VPS, com o bloco da porta 80 do domínio já tendo a location
# /.well-known/acme-challenge/ (e `make reload-nginx` feito).
#
# Uso: infra/certbot/emitir.sh dominio1.com.br dominio2.site ...
#
# Só emite o domínio principal (sem www): os www. não têm DNS hoje e o certbot
# falharia. Se um dia um www. passar a resolver, emitir à mão com -d extra.
set -uo pipefail
cd "$(dirname "$0")/../.."

if [ $# -eq 0 ]; then
    echo "Uso: $0 dominio [dominio ...]" >&2
    exit 1
fi

# Arquivo de teste no webroot do desafio: antes de pedir o certificado, confere
# que http://<dominio>/.well-known/acme-challenge/ chega nesse webroot. Sem isso,
# um reload esquecido gastaria tentativas no limite de falhas da Let's Encrypt
# (5 por hora por domínio).
token="teste-$(date +%s)"
docker compose run --rm --entrypoint sh certbot -c \
    "mkdir -p /var/www/certbot/.well-known/acme-challenge && echo $token > /var/www/certbot/.well-known/acme-challenge/$token" \
    || { echo "Não consegui gravar o arquivo de teste no webroot" >&2; exit 1; }

ok=()
falhou=()
for dominio in "$@"; do
    echo "=== $dominio"
    resposta=$(curl -s --max-time 10 "http://$dominio/.well-known/acme-challenge/$token" || true)
    if [ "$resposta" != "$token" ]; then
        echo "Caminho do desafio não responde (falta o bloco da porta 80 ou o make reload-nginx?)"
        falhou+=("$dominio")
        continue
    fi
    if docker compose run --rm certbot certonly --webroot \
        -w /var/www/certbot \
        -d "$dominio" --cert-name "$dominio" \
        --email admin@lsnlivros.com.br --agree-tos --no-eff-email \
        --non-interactive --keep-until-expiring; then
        ok+=("$dominio")
    else
        falhou+=("$dominio")
    fi
done

docker compose run --rm --entrypoint sh certbot -c \
    "rm -f /var/www/certbot/.well-known/acme-challenge/$token" || true

echo
echo "Emitidos: ${ok[*]:-nenhum}"
echo "Falharam: ${falhou[*]:-nenhum}"
[ ${#falhou[@]} -eq 0 ]
