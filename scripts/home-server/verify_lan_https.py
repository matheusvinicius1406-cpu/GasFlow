#!/usr/bin/env python3
"""Verificação real da borda HTTPS do Home Server pela LAN.

Faz o que o `scripts/smoke-test.sh` faz, mas **com validação TLS de verdade**:
o `curl` do Git Bash no Windows usa Schannel e ignora `--cacert`, então a
confiança no certificado da CA interna só pode ser provada por um cliente que
leia o arquivo da CA (aqui, `ssl.create_default_context(cafile=...)`).

Cada checagem é idêntica ao smoke test de deploy:
    /               200  (SPA)
    /api/health     200  (backend via nginx)
    /ready          200  (readiness)
    /api/v1/health  200  (API v1 sem strip)
    /auth/me        401  (rota raiz do backend, não fallback da SPA)
    /driver/me      401
    /metrics        404  (métricas NUNCA saem pela borda)
    login admin -> GET /api/dashboard 200

Uso (a senha vem do ambiente, nunca de argv):
    set -a && . ./deploy/home-server/.env.lab && set +a
    python scripts/home-server/verify_lan_https.py \
        --base https://192.168.0.211 \
        --ca deploy/home-server/certs/gasflow-home-ca.crt \
        --hostname gasflow.home

Exit 0 = tudo passou (incluindo a cadeia TLS validada contra a CA).
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import ssl
import urllib.error
import urllib.request

GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[0;33m"
NC = "\033[0m"


def request(
    url: str,
    context: ssl.SSLContext,
    *,
    method: str = "GET",
    body: dict | None = None,
    token: str | None = None,
) -> tuple[int, dict | str]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, context=context, timeout=20) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="ex.: https://192.168.0.211")
    parser.add_argument("--ca", required=True, help="certificado raiz da CA interna")
    parser.add_argument("--hostname", default="", help="hostname local a testar")
    parser.add_argument("--admin-user", default="admin")
    args = parser.parse_args(argv)

    password = os.environ.get("ADMIN_PASSWORD", "")
    passed = failed = 0

    def check(desc: str, expect: int, path: str) -> tuple[int, dict | str]:
        nonlocal passed, failed
        code, payload = request(args.base + path, ctx)
        if code == expect:
            print(f"{GREEN}OK{NC}    {desc} ({code})")
            passed += 1
        else:
            print(f"{RED}FAIL{NC}  {desc} (esperado {expect}, veio {code})")
            failed += 1
        return code, payload

    print(f"== HTTPS/LAN — {args.base} ==")
    try:
        ctx = ssl.create_default_context(cafile=args.ca)
    except (OSError, ssl.SSLError) as exc:
        print(f"{RED}FAIL{NC}  não foi possível carregar a CA: {exc}")
        return 1

    # A cadeia tem de ser validada de fato: create_default_context com cafile
    # e CERT_REQUIRED faz o handshake falhar se o certificado não for confiável.
    check("SPA (frontend)", 200, "/")
    check("backend /api/health", 200, "/api/health")
    check("backend /ready", 200, "/ready")
    check("api v1 (sem strip)", 200, "/api/v1/health")
    check("auth raiz (401 esperado)", 401, "/auth/me")
    check("driver raiz (401 esperado)", 401, "/driver/me")
    check("metrics bloqueado na borda", 404, "/metrics")

    if password:
        code, payload = request(
            args.base + "/api/auth/login",
            ctx,
            method="POST",
            body={"username": args.admin_user, "password": password},
        )
        token = (
            payload.get("token") or payload.get("access_token")
            if isinstance(payload, dict)
            else None
        )
        if code == 200 and token:
            print(f"{GREEN}OK{NC}    login admin (200)")
            passed += 1
            code2, _ = request(args.base + "/api/dashboard", ctx, token=token)
            if code2 == 200:
                print(f"{GREEN}OK{NC}    GET /api/dashboard autenticado (200)")
                passed += 1
            else:
                print(f"{RED}FAIL{NC}  GET /api/dashboard autenticado ({code2})")
                failed += 1
        else:
            print(f"{RED}FAIL{NC}  login admin (HTTP {code}, sem token)")
            failed += 1
    else:
        print(f"{YELLOW}SKIP{NC}  login: ADMIN_PASSWORD não definido no ambiente")
        failed += 1

    if args.hostname:
        try:
            ip = socket.gethostbyname(args.hostname)
            print(f"{GREEN}OK{NC}    DNS {args.hostname} -> {ip}")
            passed += 1
        except OSError:
            print(
                f"{YELLOW}AVISO{NC} {args.hostname} não resolve neste host "
                "(esperado sem reserva DHCP/DNS: use o IP ou /etc/hosts)"
            )

    print("=" * 41)
    print(f"Resultado: {GREEN}{passed} ok{NC} / {RED}{failed} falhas{NC}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
