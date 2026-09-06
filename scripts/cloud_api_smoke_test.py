#!/usr/bin/env python3
"""
Cloud API Smoke Test — valida a ativação do canal oficial da Meta.

Uso (a partir de GasFlow/backend, com as env vars configuradas):

    # 1. Conferir credenciais e qualidade do número (não envia nada)
    python ../scripts/cloud_api_smoke_test.py --check-config

    # 2. Enviar texto livre (só funciona dentro da janela de 24h do usuário)
    python ../scripts/cloud_api_smoke_test.py --send-text 5591999999999 "Teste GasFlow"

    # 3. Enviar template aprovado (funciona a qualquer momento — campanhas)
    python ../scripts/cloud_api_smoke_test.py \
        --send-template 5591999999999 entrega_confirmada \
        --lang pt_BR --params "João" "Pedido #42"

    # 4. Verificar o webhook publicado (handshake de ponta a ponta)
    python ../scripts/cloud_api_smoke_test.py \
        --verify-webhook https://api.seudominio.com/api/v1

Env lidas:
    WHATSAPP_CLOUD_API_TOKEN, WHATSAPP_CLOUD_API_PHONE_NUMBER_ID,
    WHATSAPP_CLOUD_API_VERSION, WHATSAPP_CLOUD_API_VERIFY_TOKEN

Códigos de saída: 0 = ok, 1 = falha de configuração, 2 = falha de chamada.
"""

import argparse
import os
import secrets
import sys

import httpx

# Windows (cp1252) não imprime emojis — força UTF-8 com fallback seguro.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

TOKEN = os.getenv("WHATSAPP_CLOUD_API_TOKEN", "")
PHONE_ID = os.getenv("WHATSAPP_CLOUD_API_PHONE_NUMBER_ID", "")
VERSION = os.getenv("WHATSAPP_CLOUD_API_VERSION", "v21.0")
VERIFY_TOKEN = os.getenv("WHATSAPP_CLOUD_API_VERIFY_TOKEN", "")
BASE = f"https://graph.facebook.com/{VERSION}"


def headers() -> dict:
    return {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def require_config() -> bool:
    missing = [
        k
        for k, v in {
            "WHATSAPP_CLOUD_API_TOKEN": TOKEN,
            "WHATSAPP_CLOUD_API_PHONE_NUMBER_ID": PHONE_ID,
        }.items()
        if not v
    ]
    if missing:
        print(f"[FALHA] Config ausente: {', '.join(missing)}")
        print("   Defina as variáveis no .env ou no ambiente antes de rodar.")
        return False
    return True


def check_config() -> int:
    if not require_config():
        return 1
    print(f"→ GET {BASE}/{PHONE_ID} (valida token e número)")
    resp = httpx.get(
        f"{BASE}/{PHONE_ID}",
        headers=headers(),
        params={"fields": "verified_name,display_phone_number,quality_rating,platform"},
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"[FALHA] HTTP {resp.status_code}: {resp.text[:300]}")
        if resp.status_code in (401, 403):
            print(
                "   Token inválido/expirado ou sem permissão whatsapp_business_messaging."
            )
        return 2
    data = resp.json()
    print("[OK] Credenciais válidas:")
    print(f"   Número exibido : {data.get('display_phone_number')}")
    print(f"   Nome verificado: {data.get('verified_name')}")
    print(f"   Qualidade      : {data.get('quality_rating', 'UNKNOWN')}")
    print(f"   Plataforma     : {data.get('platform')}")
    quality = data.get("quality_rating", "")
    if quality and quality not in ("GREEN", "UNKNOWN"):
        print(
            "   [ATENÇÃO] Qualidade abaixo de GREEN — revise o volume antes de campanhas."
        )
    return 0


def send_text(to: str, text: str) -> int:
    if not require_config():
        return 1
    print(f"→ POST messages (text → {to})")
    resp = httpx.post(
        f"{BASE}/{PHONE_ID}/messages",
        headers=headers(),
        json={
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"preview_url": True, "body": text},
        },
        timeout=30,
    )
    if resp.status_code in (200, 201):
        print(f"[OK] Enviado: {resp.json().get('messages', [{}])[0].get('id')}")
        return 0
    print(f"[FALHA] HTTP {resp.status_code}: {resp.text[:400]}")
    if "131047" in resp.text:
        print("   Fora da janela de 24h — use --send-template (template aprovado).")
    return 2


def send_template(to: str, template: str, lang: str, params: list[str]) -> int:
    if not require_config():
        return 1
    payload: dict = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "template",
        "template": {"name": template, "language": {"code": lang}},
    }
    if params:
        payload["template"]["components"] = [
            {
                "type": "body",
                "parameters": [{"type": "text", "text": p} for p in params],
            }
        ]
    print(f"→ POST messages (template '{template}' → {to})")
    resp = httpx.post(
        f"{BASE}/{PHONE_ID}/messages", headers=headers(), json=payload, timeout=30
    )
    if resp.status_code in (200, 201):
        print(
            f"[OK] Template enviado: {resp.json().get('messages', [{}])[0].get('id')}"
        )
        return 0
    print(f"[FALHA] HTTP {resp.status_code}: {resp.text[:400]}")
    if "132000" in resp.text:
        print(
            "   Template inexistente/não aprovado neste WABA — confira no Meta Business."
        )
    return 2


def verify_webhook(api_base: str) -> int:
    if not VERIFY_TOKEN:
        print("[FALHA] WHATSAPP_CLOUD_API_VERIFY_TOKEN não configurado.")
        return 1
    challenge = secrets.token_hex(12)
    url = f"{api_base.rstrip('/')}/whatsapp/cloud-api/webhook"
    print(f"→ GET {url} (handshake de subscrição)")
    resp = httpx.get(
        url,
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": VERIFY_TOKEN,
            "hub.challenge": challenge,
        },
        timeout=15,
    )
    if resp.status_code == 200 and resp.text.strip() == challenge:
        print("[OK] Webhook respondeu o challenge corretamente.")
        return 0
    print(f"[FALHA] HTTP {resp.status_code}, body: {resp.text[:200]!r}")
    print("   Esperado: 200 com o challenge ecoado. Verifique a URL pública,")
    print("   o VERIFY_TOKEN no servidor e o TLS do domínio.")
    return 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Cloud API smoke test (GasFlow)")
    parser.add_argument(
        "--check-config", action="store_true", help="valida token e número"
    )
    parser.add_argument("--send-text", nargs=2, metavar=("TO", "TEXT"))
    parser.add_argument("--send-template", nargs=2, metavar=("TO", "TEMPLATE"))
    parser.add_argument("--lang", default="pt_BR")
    parser.add_argument("--params", nargs="*", default=[])
    parser.add_argument(
        "--verify-webhook",
        metavar="API_BASE",
        help="ex.: https://api.seudominio.com/api/v1",
    )
    args = parser.parse_args()

    if args.check_config:
        return check_config()
    if args.send_text:
        return send_text(args.send_text[0], args.send_text[1])
    if args.send_template:
        return send_template(
            args.send_template[0], args.send_template[1], args.lang, args.params
        )
    if args.verify_webhook:
        return verify_webhook(args.verify_webhook)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
