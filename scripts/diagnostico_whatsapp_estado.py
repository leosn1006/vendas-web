"""
Diagnostico de estado da conta WhatsApp Business API (somente leitura).

Consulta, via GET, o estado atual do token, da(s) WABA(s) acessiveis por ele e
dos numeros de telefone vinculados: debug_token, account_review_status,
business_verification_status, quality_rating, status e health_status.

Nao envia nenhuma mensagem nem faz nenhuma escrita na API — apenas GET.

A API do Graph nao expõe historico retroativo de eventos/violacoes (os webhooks
account_update e phone_number_quality_update sao push-only; sem uma inscricao
ativa gravando esses eventos no momento em que ocorreram, nao ha como recupera-los
depois). O que este script mostra e o ESTADO ATUAL, nao um historico.

Uso:
    python scripts/diagnostico_whatsapp_estado.py
"""
import json
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

API_VERSION = "v24.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"

TOKEN_ENV_VAR = "WHATSAPP_ACCESS_TOKEN_LSN"
WABA_FALLBACK_ENV_VAR = "WHATSAPP_BUSINESS_ACCOUNT_ID"

# Ponto de partida conhecido: um api_phone_number_id da tabela `telefones_produto`
# (token_env_key = 'WHATSAPP_ACCESS_TOKEN_LSN'). Preencha aqui ou passe como
# argumento de linha de comando: python scripts/diagnostico_whatsapp_estado.py <phone_number_id>
PHONE_NUMBER_ID_CONHECIDO = ""

WABA_FIELDS = "id,name,account_review_status,business_verification_status,health_status"
BUSINESS_FIELDS = "id,name,verification_status,whatsapp_business_manager_messaging_limit"
PHONE_FIELDS = (
    "id,display_phone_number,verified_name,quality_rating,status,"
    "name_status,code_verification_status,health_status"
)


def mascarar(token: str) -> str:
    if not token or len(token) < 14:
        return "(vazio)"
    return f"{token[:8]}...{token[-6:]} ({len(token)} chars)"


def chamar(path: str, token: str, **params) -> tuple[int, dict]:
    params["access_token"] = token
    try:
        resp = requests.get(f"{BASE_URL}/{path}", params=params, timeout=20)
    except requests.RequestException as e:
        return 0, {"erro_local": str(e)}
    try:
        data = resp.json()
    except ValueError:
        data = {"raw": resp.text}
    return resp.status_code, data


def imprimir_json(titulo: str, status: int, data: dict) -> None:
    print(f"\n--- {titulo} (HTTP {status}) ---")
    print(json.dumps(data, indent=2, ensure_ascii=False))


def extrair_wabas_do_debug_token(debug_data: dict) -> set[str]:
    wabas = set()
    info = debug_data.get("data", {}) or {}
    for escopo in info.get("granular_scopes", []) or []:
        if escopo.get("scope") in ("whatsapp_business_management", "whatsapp_business_messaging"):
            for target_id in escopo.get("target_ids", []) or []:
                wabas.add(target_id)
    return wabas


def extrair_entidades_do_health_status(health_data: dict) -> dict:
    """A partir do health_status de um número, extrai os IDs de WABA/BUSINESS/APP
    presentes na cadeia (entities), sem precisar adivinhar nada."""
    entidades = {}
    chain = (health_data.get("health_status") or {}).get("entities", [])
    for item in chain:
        tipo = item.get("entity_type")
        if tipo and item.get("id"):
            entidades[tipo] = item
    return entidades


def diagnosticar_via_phone_number_id(phone_number_id: str, token: str) -> None:
    print("\n" + "#" * 78)
    print(f"# Descoberta via api_phone_number_id conhecido: {phone_number_id}")
    print("#" * 78)

    fields = PHONE_FIELDS
    status, phone_data = chamar(phone_number_id, token, fields=fields)
    imprimir_json(f"Número {phone_number_id} — estado + health_status (cadeia completa)", status, phone_data)

    entidades = extrair_entidades_do_health_status(phone_data)
    if not entidades:
        print("\nNão veio 'entities' no health_status (numero pode estar sem acesso/deletado). Parando por aqui.")
        return

    print("\n>> IDs descobertos na cadeia do health_status:")
    for tipo, item in entidades.items():
        print(f"   {tipo}: id={item.get('id')} can_send_message={item.get('can_send_message')}")

    waba = entidades.get("WABA")
    if waba:
        waba_id = waba["id"]
        status, waba_data = chamar(waba_id, token, fields=WABA_FIELDS)
        imprimir_json(f"WABA {waba_id} — estado da conta", status, waba_data)

        status, numeros_data = chamar(f"{waba_id}/phone_numbers", token, fields=PHONE_FIELDS)
        imprimir_json(f"WABA {waba_id} — TODOS os números vinculados", status, numeros_data)

    business = entidades.get("BUSINESS")
    if business:
        business_id = business["id"]
        status, business_data = chamar(business_id, token, fields=BUSINESS_FIELDS)
        imprimir_json(f"Business Portfolio {business_id} — estado + limite compartilhado", status, business_data)


def main() -> None:
    token = os.getenv(TOKEN_ENV_VAR, "")
    if not token:
        print(f"Variavel {TOKEN_ENV_VAR} nao encontrada no .env — nada a fazer.")
        sys.exit(1)

    print("=" * 78)
    print("DIAGNOSTICO DE ESTADO — WHATSAPP BUSINESS API (somente leitura)")
    print("=" * 78)
    print(f"Token usado ({TOKEN_ENV_VAR}): {mascarar(token)}")

    # 1) debug_token: validade, app associado, escopos, e (se presentes) as WABAs
    #    que esse token enxerga — evita ter que adivinhar o WABA ID na mao.
    status, debug_data = chamar("debug_token", token, input_token=token)
    imprimir_json("1) debug_token — validade e escopos do token", status, debug_data)

    info = (debug_data.get("data") or {})
    is_valid = info.get("is_valid")
    print(f"\n>> is_valid: {is_valid}")
    if info.get("error"):
        print(f">> erro reportado pelo debug_token: {info['error']}")

    phone_number_id = (sys.argv[1] if len(sys.argv) > 1 else "") or PHONE_NUMBER_ID_CONHECIDO
    if phone_number_id:
        diagnosticar_via_phone_number_id(phone_number_id, token)
        print("\n" + "=" * 78)
        print(
            "Nota: isto e o ESTADO ATUAL. A Graph API nao tem endpoint de historico\n"
            "retroativo de violacoes/alertas (account_update e phone_number_quality_update\n"
            "sao push-only) — esse historico so existe na aba Account Quality do\n"
            "WhatsApp Manager, manualmente, nao via GET."
        )
        print("=" * 78)
        return

    wabas = extrair_wabas_do_debug_token(debug_data)
    if not wabas:
        fallback = os.getenv(WABA_FALLBACK_ENV_VAR, "")
        if fallback:
            print(
                f"\nNenhuma WABA encontrada nos granular_scopes do token. "
                f"Tentando com {WABA_FALLBACK_ENV_VAR}={fallback} (pode nao ser "
                f"a WABA correta para este token especifico)."
            )
            wabas = {fallback}
        else:
            print(
                "\nNenhuma WABA encontrada nos granular_scopes do token, e nao ha "
                f"{WABA_FALLBACK_ENV_VAR} no .env para tentar como fallback. "
                "Nao e possivel continuar a descoberta automatica."
            )
            return

    # 2) Para cada WABA candidata: estado da conta + health_status agregado
    #    (o health_status de uma WABA ja encadeia app -> portfolio -> WABA).
    for waba_id in wabas:
        status, waba_data = chamar(waba_id, token, fields=WABA_FIELDS)
        imprimir_json(f"2) WABA {waba_id} — estado da conta", status, waba_data)

        status, health_data = chamar(waba_id, token, fields="health_status")
        imprimir_json(f"2b) WABA {waba_id} — health_status (app/portfolio/WABA)", status, health_data)

        # 3) Numeros vinculados a essa WABA
        status, numeros_data = chamar(f"{waba_id}/phone_numbers", token, fields=PHONE_FIELDS)
        imprimir_json(f"3) WABA {waba_id} — numeros de telefone vinculados", status, numeros_data)

    print("\n" + "=" * 78)
    print(
        "Nota: isto e o ESTADO ATUAL. A Graph API nao tem endpoint de historico\n"
        "retroativo de violacoes/alertas (account_update e phone_number_quality_update\n"
        "sao push-only) — esse historico so existe na aba Account Quality do\n"
        "WhatsApp Manager, manualmente, nao via GET."
    )
    print("=" * 78)


if __name__ == "__main__":
    main()
