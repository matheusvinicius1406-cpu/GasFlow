#!/usr/bin/env python3
"""MOBILE USB LAB 01 - smoke test / evidencia de comunicacao API (laboratorio).

Verifica, sem imprimir segredos nem tokens:

  1. GET  /health                    - backend vivo
  2. POST /auth/login (admin lab)    - autenticacao do tenant de lab
  3. GET  /auth/tenants              - tenant gasflow_lab presente
  4. POST /auth/login (entregador)   - credencial de lab valida
  5. GET  /auth/me                   - sessao do entregador
  6. GET  /driver/me                 - identidade do entregador
  7. GET  /driver/deliveries         - entregas ficticias visiveis
  8. conteudo esperado               - LAB-001..LAB-005 nos estados do roteiro

Exit code 0 = todos os cheques passaram; 1 = pelo menos um falhou.

Uso:  python verify_lab_api.py [--api http://127.0.0.1:8010]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

LAB_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", "."), "Temp", "opencode", "gasflow-lab"
)
SECRETS = os.path.join(LAB_DIR, "secrets.env")

EXPECTED_STATES = {
    "LAB-001": "PENDING",
    "LAB-002": "ASSIGNED",
    "LAB-003": "EN_ROUTE",
    "LAB-004": "PENDING",
    "LAB-005": "ASSIGNED",
}

_results: list[tuple[bool, str]] = []


def check(ok: bool, label: str, detail: str = "") -> bool:
    _results.append((ok, label))
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {label}" + (f" -> {detail}" if detail else ""))
    return ok


def call(
    method: str, path: str, payload=None, token: str | None = None, base: str = ""
) -> tuple[int, dict | list]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    r = urllib.request.Request(f"{base}{path}", data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, (json.loads(body) if body.strip() else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"detail": raw[:200]}
    except urllib.error.URLError as exc:
        return 0, {"detail": str(exc.reason)}


def load_secrets() -> dict:
    if not os.path.isfile(SECRETS):
        sys.exit(
            f"[verify] FALTA {SECRETS} - rode start_lab_backend.ps1 e seed_lab_data.py."
        )
    out = {}
    with open(SECRETS, encoding="ascii") as fh:
        for line in fh:
            if "=" in line:
                k, v = line.rstrip("\n").split("=", 1)
                out[k] = v
    return out


def report_deliveries(base: str, token: str) -> None:
    """Cheques 6-8: identidade do entregador e conteudo do roteiro ficticio."""
    st, dme = call("GET", "/driver/me", token=token, base=base)
    check(
        st == 200,
        "GET /driver/me (identidade do entregador)",
        f"http={st} {json.dumps(dme)[:160]}",
    )

    st, dl = call("GET", "/driver/deliveries", token=token, base=base)
    items = dl.get("deliveries", []) if isinstance(dl, dict) else []
    check(st == 200, "GET /driver/deliveries", f"http={st} itens={len(items)}")

    by_ref: dict[str, str] = {}
    for d in items:
        note = str(d.get("notes") or "")
        ref = note.split("|")[0].strip()
        by_ref[ref] = str(d.get("status"))
    ok_all = True
    for ref, expected in EXPECTED_STATES.items():
        got = by_ref.get(ref)
        ok = got == expected
        ok_all = ok_all and ok
        print(
            f"   [{'PASS' if ok else 'FAIL'}] {ref}: esperado={expected} obtido={got or 'AUSENTE'}"
        )
    check(ok_all, "LAB-001..LAB-005 nos estados do roteiro")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8010")
    args = ap.parse_args()
    base = args.api.rstrip("/")
    sec = load_secrets()

    # 1. health
    st, body = call("GET", "/health", base=base)
    check(
        st == 200 and isinstance(body, dict) and body.get("status") == "healthy",
        "GET /health",
        f"status={st} {body.get('status') if isinstance(body, dict) else ''}",
    )

    # 2. login do admin do laboratorio
    st, lg = call(
        "POST",
        "/auth/login",
        {
            "username": "admin_lab",
            "password": sec["LAB_TENANT_ADMIN_PW"],
            "platform": "desktop",
        },
        base=base,
    )
    lab_tok = (
        (lg.get("access_token") or lg.get("token")) if isinstance(lg, dict) else None
    )
    check(
        st == 200 and bool(lab_tok),
        "POST /auth/login (admin de laboratorio)",
        f"http={st}",
    )
    if isinstance(lg, dict):
        check(
            lg.get("tenant_id") == "gasflow_lab",
            "sessao pertence ao tenant gasflow_lab",
            f"tenant_id={lg.get('tenant_id')} role={lg.get('role')}",
        )

    # 3. tenant listado
    if lab_tok:
        st, tenants = call("GET", "/auth/tenants", token=lab_tok, base=base)
        items = (
            tenants
            if isinstance(tenants, list)
            else tenants.get("tenants", [])
            if isinstance(tenants, dict)
            else []
        )
        found = any(
            isinstance(t, dict) and t.get("tenant_id") == "gasflow_lab" for t in items
        )
        check(found, "tenant 'GasFlow Laboratorio' cadastrado", f"total={len(items)}")

    # 4. login do entregador
    st, dlg = call(
        "POST",
        "/auth/login",
        {
            "username": sec["LAB_DRIVER_USERNAME"],
            "password": sec["LAB_DRIVER_PASSWORD"],
            "platform": "mobile",
        },
        base=base,
    )
    drv_access = (dlg.get("access_token") or "") if isinstance(dlg, dict) else ""
    drv_opaque = (dlg.get("token") or "") if isinstance(dlg, dict) else ""
    check(
        st == 200 and bool(drv_access or drv_opaque),
        "POST /auth/login (entregador)",
        f"http={st}",
    )
    if isinstance(dlg, dict):
        check(
            bool(dlg.get("must_change_password")) is False,
            "entregador sem troca de senha pendente",
            f"must_change_password={dlg.get('must_change_password')}",
        )
        check(
            dlg.get("tenant_id") == "gasflow_lab",
            "sessao do entregador no tenant de lab",
            f"tenant_id={dlg.get('tenant_id')} role={dlg.get('role')}",
        )

    # 5/6. sessao e identidade (testa os DOIS formatos de token)
    token_used = ""
    if drv_access:
        st, me = call("GET", "/auth/me", token=drv_access, base=base)
        if check(st == 200, "GET /auth/me com access JWT", f"http={st}"):
            token_used = drv_access
    if not token_used and drv_opaque:
        st, me = call("GET", "/auth/me", token=drv_opaque, base=base)
        if check(st == 200, "GET /auth/me com token opaco", f"http={st}"):
            token_used = drv_opaque

    if token_used:
        # 6-8. identidade, entregas visiveis e conteudo do roteiro
        report_deliveries(base, token_used)
    else:
        check(False, "nenhum token do entregador aceito por /auth/me")

    failed = [lbl for ok, lbl in _results if not ok]
    print(
        f"\n[verify] {len(_results) - len(failed)}/{len(_results)} checagens passaram"
    )
    if failed:
        print("[verify] falhas: " + "; ".join(failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
