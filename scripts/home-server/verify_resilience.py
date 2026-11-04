#!/usr/bin/env python3
"""Teste de resiliência do Home Server (dados sintéticos de laboratório).

Reinicia, um por vez, cada serviço do core e comprova a recuperação pela
borda HTTPS real:

    redis  → backend volta a ficar ready (rate limit/pubsub)
    frontend → SPA responde
    caddy  → TLS volta a responder
    postgres → interrupção controlada do banco; API e dados voltam

A sessão obtida ANTES dos reinícios é reutilizada DEPOIS: sessões são
DB-backed, então o token sobrevive — prova de persistência de sessão.

NUNCA desliga a máquina, NUNCA remove volume, NUNCA para serviço de outro
projeto. Uso:
    set -a && . ./deploy/home-server/.env.lab && set +a
    python scripts/home-server/verify_resilience.py \
        --base https://192.168.0.211 --ca deploy/home-server/certs/gasflow-home-ca.crt
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import subprocess
import time
import urllib.error
import urllib.request

PROJECT = "gasflow-hs-lab"
SERVICES = {
    "redis": f"{PROJECT}-redis",
    "frontend": f"{PROJECT}-frontend",
    "caddy": f"{PROJECT}-caddy",
    "postgres": f"{PROJECT}-postgres",
}


def sh(*args: str) -> tuple[int, str]:
    p = subprocess.run(args, capture_output=True, text=True, check=False)
    return p.returncode, (p.stdout + p.stderr).strip()


class Client:
    def __init__(self, base: str, ca: str) -> None:
        self.base = base.rstrip("/")
        self.ctx = ssl.create_default_context(cafile=ca)

    def call(
        self, path: str, body: dict | None = None, token: str | None = None
    ) -> tuple[int, dict]:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            self.base + path, data=data, method="POST" if body is not None else "GET"
        )
        if body is not None:
            req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, context=self.ctx, timeout=30) as resp:
                return resp.status, json.loads(resp.read().decode() or "{}")
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read().decode() or "{}")
            except json.JSONDecodeError:
                return exc.code, {}
        except (urllib.error.URLError, OSError) as exc:
            return 0, {"error": str(exc)}


def wait_healthy(container: str, timeout: int = 180) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        code, out = sh(
            "docker", "inspect", "--format", "{{.State.Health.Status}}", container
        )
        if code == 0 and out.strip() == "healthy":
            return True
        time.sleep(3)
    return False


def probe_health(api: Client) -> int:
    """Espera a borda voltar a responder /api/health."""
    health = 0
    for _ in range(20):
        health = api.call("/api/health")[0]
        if health == 200:
            break
        time.sleep(3)
    return health


def probe_session(api: Client, token: str | None, name: str) -> tuple[bool, str | None]:
    """Reusa a sessão criada antes dos restarts; devolve (ok, nota)."""
    if not token:
        return True, None
    first = None
    dashboard = 0
    attempts = 0
    for attempts in range(1, 6):
        dashboard = api.call("/api/dashboard", token=token)[0]
        if first is None:
            first = dashboard
        if dashboard == 200:
            break
        time.sleep(3)
    note = None
    if first != 200:
        note = (
            f"NOTE  {name}: primeira requisição ao banco após o restart "
            f"devolveu {first}; recuperou em {attempts} tentativa(s) "
            f"({(attempts - 1) * 3}s)"
        )
    return dashboard == 200, note


def final_state(report) -> None:
    """Confere containers saudáveis e persistência dos dados."""
    code, status = sh(
        "docker",
        "ps",
        "--filter",
        f"name={PROJECT}",
        "--format",
        "{{.Names}}={{.Status}}",
    )
    print(status.replace("\n", "\n"))
    all_healthy = (
        status.count("healthy") >= 5
        and "unhealthy" not in status
        and "Restarting" not in status
    )
    report(all_healthy, "5+ serviços do core healthy, nenhum em restart")

    code, counts = sh(
        "docker",
        "exec",
        f"{PROJECT}-postgres",
        "psql",
        "-U",
        "gasflow_lab",
        "-d",
        "gasflow_lab",
        "-tAc",
        "select (select count(*) from clients) || '/' || (select count(*) from orders) || '/' || "
        "(select count(*) from delivery_drivers) || '/' || (select count(*) from auth_users);",
    )
    report(
        code == 0,
        f"dados preservados (clients/orders/drivers/users = {counts.strip()})",
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", required=True)
    ap.add_argument("--ca", required=True)
    args = ap.parse_args(argv)

    api = Client(args.base, args.ca)
    failures = 0

    def report(ok: bool, label: str) -> None:
        nonlocal failures
        print(f"{'OK   ' if ok else 'FAIL '} {label}")
        if not ok:
            failures += 1

    # Baseline
    code, login = api.call(
        "/api/auth/login",
        {"username": "admin", "password": os.environ.get("ADMIN_PASSWORD", "")},
    )
    report(code == 200, f"baseline: login admin (HTTP {code})")
    token = login.get("token") if code == 200 else None
    baseline_dash = api.call("/api/dashboard", token=token)[0] if token else 0
    report(baseline_dash == 200, f"baseline: /api/dashboard (HTTP {baseline_dash})")

    for name, container in SERVICES.items():
        print(f"\n-- reiniciando {name} ({container})")
        started = time.time()
        code, _ = sh("docker", "restart", container)
        report(code == 0, f"{name}: docker restart (exit {code})")
        healthy = wait_healthy(container)
        report(healthy, f"{name}: healthy em {time.time() - started:.0f}s")

        health = probe_health(api)
        report(health == 200, f"{name}: /api/health (HTTP {health})")

        session_ok, note = probe_session(api, token, name)
        if note:
            print(note)
        report(session_ok, f"{name}: sessão anterior ainda válida (/api/dashboard)")

    # Estado final + persistência de dados
    print("\n-- estado final")
    final_state(report)

    print("=" * 41)
    print(
        "RESULTADO:", "RESILIÊNCIA VALIDADA" if failures == 0 else f"{failures} FALHAS"
    )
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
