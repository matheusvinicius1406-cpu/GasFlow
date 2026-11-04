#!/usr/bin/env python3
"""Provisiona o tenant de laboratório do Home Server via API oficial.

Cria, EXCLUSIVAMENTE no banco de laboratório (`gasflow_lab`, PostgreSQL do
Home Server), usando apenas endpoints HTTP oficiais — nenhum INSERT direto:

    tenant       gasflow_home_server_lab  ("GasFlow Home Server Lab")
    admin        lab_admin      (role ADMIN)
    operador     lab_operador   (role OPERATOR)
    entregador   lab_entregador (role DRIVER + delivery_drivers)
    2 produtos fictícios, 3 clientes fictícios, 2 pedidos fictícios
    entregas atribuídas ao entregador sintético

Idempotente: cada recurso é procurado antes de ser criado; reexecutar não
duplica nada nem sobrescreve senha existente.

NÃO usa dados da Marcos Gás. NÃO envia WhatsApp. NÃO emite fiscal.

Segredos: as senhas geradas são gravadas em
`<tempdir>/gasflow-hs-lab/lab-credentials.txt` (fora do repositório) e nunca
impressas em stdout/log.

Uso:
    set -a && . ./deploy/home-server/.env.lab && set +a
    python scripts/home-server/seed_homeserver_lab.py \
        --base https://192.168.0.211 \
        --ca deploy/home-server/certs/gasflow-home-ca.crt
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import secrets
import ssl
import tempfile
import time
import urllib.error
import urllib.request

TENANT_ID = "gasflow_home_server_lab"
TENANT_NAME = "GasFlow Home Server Lab"
ADMIN_USER = "lab_admin"
OPERATOR_USER = "lab_operador"
DRIVER_USER = "lab_entregador"
DRIVER_NAME = "Entregador Sintetico Lab"
DRIVER_PHONE = "11999990000"
DRIVER_DOCUMENT = "MOTORISTA-HS-LAB-001"

PRODUCTS = [("Gas P13 (lab)", "GAS", 100.0), ("Agua 20L (lab)", "AGUA", 12.0)]
CLIENTS = [
    ("Cliente Lab Um", "11988880001", "Rua Sintetica A", "10", "Bairro Teste"),
    ("Cliente Lab Dois", "11988880002", "Rua Sintetica B", "20", "Bairro Teste"),
    ("Cliente Lab Tres", "11988880003", "Rua Sintetica C", "30", "Bairro Teste"),
]

LAB_DIR = pathlib.Path(
    os.environ.get("GASFLOW_HS_LAB_DIR")
    or pathlib.Path(tempfile.gettempdir()) / "gasflow-hs-lab"
)
CRED_FILE = LAB_DIR / "lab-credentials.txt"


class Api:
    def __init__(self, base: str, ca: str) -> None:
        self.base = base.rstrip("/")
        self.ctx = ssl.create_default_context(cafile=ca)

    def call(
        self,
        path: str,
        body: dict | None = None,
        token: str | None = None,
        method: str | None = None,
    ) -> tuple[int, dict]:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            self.base + path,
            data=data,
            method=method or ("POST" if body is not None else "GET"),
        )
        if body is not None:
            req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, context=self.ctx, timeout=30) as resp:
                raw = resp.read().decode() or "{}"
                try:
                    return resp.status, json.loads(raw)
                except json.JSONDecodeError:
                    return resp.status, {"raw": raw[:200]}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode() or "{}"
            try:
                return exc.code, json.loads(raw)
            except json.JSONDecodeError:
                return exc.code, {"raw": raw[:200]}

    def login(
        self, username: str, password: str, attempts: int = 4
    ) -> tuple[int, dict]:
        """Login com backoff para o rate limit oficial (10/min/IP)."""
        code, body = 0, {}
        for attempt in range(1, attempts + 1):
            code, body = self.call(
                "/api/auth/login", {"username": username, "password": password}
            )
            if code != 429:
                break
            wait = 15 * attempt
            print(f"     rate limit no login ({username}); aguardando {wait}s...")
            time.sleep(wait)
        if code == 200:
            body["_token"] = body.get("token") or body.get("access_token")
        return code, body


def strong_password() -> str:
    """Senha forte que passa a política (maiúscula, minúscula, dígito)."""
    return "Lab" + secrets.token_urlsafe(18) + "9"


def load_credentials() -> dict[str, str]:
    """Credenciais já emitidas em execuções anteriores (arquivo fora do repo)."""
    if not CRED_FILE.exists():
        return {}
    creds: dict[str, str] = {}
    for line in CRED_FILE.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            if value:
                creds[key] = value
    return creds


def write_credentials(created: dict[str, str]) -> None:
    """Acrescenta credenciais novas sem duplicar e sem apagar as existentes."""
    if not created:
        return
    existing = CRED_FILE.read_text(encoding="utf-8") if CRED_FILE.exists() else ""
    with CRED_FILE.open("a", encoding="utf-8", newline="\n") as fh:
        if not existing:
            fh.write(
                "# GasFlow Home Server LAB — credenciais sintéticas (NAO versionar)\n"
            )
        for username, password in created.items():
            if f"{username}=" not in existing:
                fh.write(f"{username}={password}\n")
    print(f"OK credenciais gravadas em {CRED_FILE} (fora do repositório)")


def bootstrap(api: Api, admin_password: str) -> str | None:
    code, body = api.login("admin", admin_password)
    if code != 200:
        print(f"ERRO: login bootstrap falhou (HTTP {code})")
        return None
    print(
        f"OK login bootstrap (tenant={body.get('tenant_id')}, role={body.get('role')})"
    )
    return body["_token"]


def ensure_tenant(api: Api, token: str) -> bool:
    code, body = api.call(
        "/api/auth/tenants", {"tenant_id": TENANT_ID, "name": TENANT_NAME}, token
    )
    if code == 200:
        print(f"OK tenant criado: {TENANT_ID}")
        return True
    if code == 400:
        print(f"OK tenant já existia: {TENANT_ID}")
        return True
    print(f"ERRO ao criar tenant (HTTP {code}): {body}")
    return False


def find_user_id(api: Api, token: str, username: str) -> str | None:
    code, body = api.call("/api/admin/users", token=token)
    if code != 200:
        return None
    items = body.get("users") or body.get("items") or []
    for item in items:
        if item.get("username") == username:
            return item.get("id")
    return None


def ensure_user(
    api: Api,
    token: str,
    created: dict[str, str],
    username: str,
    role: str,
) -> str | None:
    """Cria o usuário ou redefine a senha por endpoint oficial."""
    known = load_credentials().get(username)
    if known and api.login(username, known)[0] == 200:
        print(f"OK usuário já provisionado: {username} ({role})")
        created[username] = known
        return known

    password = strong_password()
    code, body = api.call(
        "/api/auth/users",
        {
            "username": username,
            "email": f"{username}@{TENANT_ID}.lab",
            "password": password,
            "display_name": f"{username} (lab)",
            "role": role,
            "tenant_id": TENANT_ID,
        },
        token,
    )
    if code in (200, 201):
        print(f"OK usuário criado: {username} ({role})")
        created[username] = password
        return password

    print(f"INFO usuário {username} já existia (HTTP {code}); redefinindo senha")
    user_id = find_user_id(api, token, username)
    if not user_id:
        print(f"ERRO: não foi possível localizar {username} para reset")
        return None
    code_r, reset = api.call(f"/api/admin/users/{user_id}/reset-password", {}, token)
    new_pw = reset.get("temporary_password") or ""
    if code_r != 200 or not new_pw:
        print(f"ERRO: reset de {username} falhou (HTTP {code_r}): {reset}")
        return None
    print(f"OK senha de {username} redefinida")
    created[username] = new_pw
    return new_pw


def lab_admin_token(api: Api, created: dict[str, str]) -> str | None:
    password = created.get(ADMIN_USER)
    if not password:
        print(
            "ERRO: senha de lab_admin desconhecida (usuário já existia em execução anterior)"
        )
        print(
            f"      recupere em {CRED_FILE} ou redefina via /api/admin/users/<id>/reset-password"
        )
        return None
    code, body = api.login(ADMIN_USER, password)
    if code != 200:
        print(f"ERRO: login de {ADMIN_USER} falhou (HTTP {code})")
        return None
    if body.get("tenant_id") != TENANT_ID:
        print(f"ERRO: sessão do admin de lab não está no tenant {TENANT_ID}")
        return None
    print(
        f"OK login {ADMIN_USER} (tenant={body.get('tenant_id')}, role={body.get('role')})"
    )
    return body["_token"]


def seed_driver(
    api: Api, token: str, created: dict[str, str]
) -> tuple[str | None, str | None]:
    driver_id = None
    driver_pw = created.get(DRIVER_USER) or load_credentials().get(DRIVER_USER)
    code, body = api.call(
        "/api/v1/admin/drivers",
        {
            "name": DRIVER_NAME,
            "phone": DRIVER_PHONE,
            "document": DRIVER_DOCUMENT,
            "username": DRIVER_USER,
        },
        token,
    )
    if code in (200, 201):
        driver_id = body.get("driver_id")
        driver_pw = body.get("temporary_password")
        print(f"OK entregador criado: {driver_id} (username={body.get('username')})")
        created[DRIVER_USER] = driver_pw or ""
    else:
        print(f"INFO entregador não criado (HTTP {code}): {body}")
        code_l, listing = api.call("/api/v1/admin/drivers", token=token)
        if code_l != 200:
            print(f"ERRO ao listar entregadores (HTTP {code_l})")
            return None, None
        for driver in listing.get("drivers") or []:
            # `_driver_payload` usa `driver_id`/`name`; `delivery_drivers.username`
            # não é preenchido pelo cadastro canônico (credencial em auth_users).
            if (
                driver.get("name") == DRIVER_NAME
                or driver.get("nome") == DRIVER_NAME
                or driver.get("username") == DRIVER_USER
            ):
                driver_id = driver.get("driver_id") or driver.get("codigo")
                break
        if driver_id:
            print(f"OK entregador já existia: {driver_id}")
            code_r, reset = api.call(
                f"/api/v1/admin/drivers/{driver_id}/reset-password", {}, token
            )
            if code_r == 200:
                driver_pw = reset.get("temporary_password")
                created[DRIVER_USER] = driver_pw or ""

    if driver_pw:
        write_credentials({DRIVER_USER: driver_pw})
    return driver_id, driver_pw


def seed_products(api: Api, token: str) -> list[str]:
    code_l, body_l = api.call("/api/v1/products/", token=token)
    if isinstance(body_l, list):
        listing = body_l
    elif isinstance(body_l, dict):
        listing = body_l.get("products") or body_l.get("items") or []
    else:
        listing = []
    existing = {(p.get("nome") or ""): p.get("codigo") for p in listing}

    codes: list[str] = []
    for name, kind, price in PRODUCTS:
        if existing.get(name):
            codes.append(existing[name])
            print(f"OK produto já existia: {name} -> {existing[name]}")
            continue
        code, body = api.call(
            "/api/v1/products/",
            {"nome": name, "tipo": kind, "preco": price, "estoque": 50},
            token,
        )
        if code in (200, 201):
            codes.append(body.get("codigo", ""))
            print(f"OK produto criado: {name} -> {body.get('codigo')}")
        else:
            print(f"AVISO produto {name} não criado (HTTP {code}): {body}")

    # Estoque vive em `inventory` (FASE 7.1), NÃO em products.estoque.
    for codigo in codes:
        code, body = api.call(
            f"/api/v1/inventory/{codigo}/entries",
            {"quantity": 50, "reason": "carga inicial de laboratorio"},
            token,
        )
        if code in (200, 201):
            inv = body.get("inventory") or {}
            print(
                f"OK estoque inicial {codigo}: {inv.get('quantity')} "
                f"(disponivel {inv.get('available_quantity')})"
            )
        else:
            print(f"INFO estoque {codigo} já carregado ou falhou (HTTP {code})")
    return codes


def seed_clients(api: Api, token: str) -> list[str]:
    code_c, body_c = api.call("/api/v1/clients/", token=token)
    listing = (
        (body_c.get("clients") or body_c.get("items") or [])
        if isinstance(body_c, dict)
        else []
    )
    existing = {(c.get("telefone") or ""): c.get("codigo") for c in listing}

    codes: list[str] = []
    for name, phone, street, number, neighborhood in CLIENTS:
        if existing.get(phone):
            codes.append(existing[phone])
            print(f"OK cliente já existia: {name} -> {existing[phone]}")
            continue
        code, body = api.call(
            "/api/v1/clients/",
            {
                "nome": name,
                "telefone": phone,
                "rua": street,
                "numero": number,
                "bairro": neighborhood,
            },
            token,
        )
        if code in (200, 201):
            codes.append(body.get("codigo", ""))
            print(f"OK cliente criado: {name} -> {body.get('codigo')}")
        elif code == 409:
            # Já existe com este telefone: recupera o código da mensagem.
            detail = str(body.get("detail", "")) if isinstance(body, dict) else ""
            match = re.search(r"c[oó]digo:\s*([0-9A-Za-z_-]+)", detail)
            if match:
                codes.append(match.group(1))
                print(f"OK cliente já existia: {name} -> {match.group(1)}")
            else:
                print(
                    f"AVISO cliente {name} existente sem código reconhecível: {detail}"
                )
        else:
            print(f"AVISO cliente {name} não criado (HTTP {code}): {body}")
    return codes


def seed_orders(api: Api, token: str, clients: list[str], products: list[str]) -> None:
    if not products:
        print("AVISO sem produto para criar pedidos")
        return
    for index, client in enumerate(clients[:2], start=1):
        if not client:
            continue
        code, body = api.call(
            "/api/v1/orders/",
            {
                "client_codigo": client,
                "items": [{"product_codigo": products[0], "quantity": index}],
                "delivery_fee": 5.0,
                "discount": 0.0,
                "payment_method": "DINHEIRO",
            },
            token,
        )
        if code in (200, 201):
            print(f"OK pedido criado: {body.get('codigo')} (cliente {client})")
        else:
            print(f"AVISO pedido do cliente {client} não criado (HTTP {code}): {body}")


def prove_operator(api: Api, created: dict[str, str]) -> None:
    password = created.get(OPERATOR_USER)
    if not password:
        return
    code, body = api.login(OPERATOR_USER, password)
    print(
        f"{'OK' if code == 200 else 'FALHA'} login {OPERATOR_USER} -> HTTP {code} "
        f"tenant={body.get('tenant_id')} role={body.get('role')}"
    )
    if code == 200:
        code_me, _ = api.call("/api/auth/me", token=body["_token"])
        print(
            f"{'OK' if code_me == 200 else 'FALHA'} GET /api/auth/me do operador -> HTTP {code_me}"
        )


def prove_driver(api: Api, driver_pw: str | None) -> None:
    """Prova o caminho suportado: auth principal + `/driver/*`."""
    if not driver_pw:
        return
    code, body = api.login(DRIVER_USER, driver_pw)
    print(
        f"{'OK' if code == 200 else 'FALHA'} POST /api/auth/login entregador -> HTTP {code} "
        f"role={body.get('role')} tenant={body.get('tenant_id')}"
    )
    if code == 200:
        token = body["_token"]
        code_me, _ = api.call("/api/v1/driver/me", token=token)
        print(
            f"{'OK' if code_me == 200 else 'FALHA'} GET /api/v1/driver/me -> HTTP {code_me}"
        )
        code_del, deliveries = api.call("/api/v1/driver/deliveries", token=token)
        count = (
            len(deliveries.get("deliveries") or deliveries.get("items") or [])
            if isinstance(deliveries, dict)
            else 0
        )
        print(
            f"{'OK' if code_del == 200 else 'FALHA'} GET /api/v1/driver/deliveries "
            f"-> HTTP {code_del} (entregas={count})"
        )

    # Contrato de token mobile (`/auth/mobile/login`): exige
    # delivery_drivers.username/password_hash, que o cadastro canônico NÃO
    # preenche (a credencial vai para auth_users). Registrado como R-3.
    code_m, mobile = api.call(
        "/api/auth/mobile/login",
        {"username": DRIVER_USER, "password": driver_pw, "device_id": "hs-lab-cli"},
    )
    if code_m == 200:
        print(
            f"OK POST /api/auth/mobile/login -> HTTP 200 (expires_in={mobile.get('expires_in')})"
        )
    else:
        print(
            f"INFO POST /api/auth/mobile/login -> HTTP {code_m} "
            "(achado R-3: credencial fica em auth_users, não em delivery_drivers)"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--ca", required=True)
    args = parser.parse_args(argv)

    admin_password = os.environ.get("ADMIN_PASSWORD", "")
    if not admin_password:
        print("ERRO: ADMIN_PASSWORD ausente no ambiente")
        return 2

    api = Api(args.base, args.ca)
    LAB_DIR.mkdir(parents=True, exist_ok=True)
    created: dict[str, str] = {}

    boot_token = bootstrap(api, admin_password)
    if not boot_token or not ensure_tenant(api, boot_token):
        return 1

    ensure_user(api, boot_token, created, ADMIN_USER, "ADMIN")
    ensure_user(api, boot_token, created, OPERATOR_USER, "OPERATOR")
    write_credentials(created)

    token = lab_admin_token(api, created)
    if not token:
        return 1

    _, driver_pw = seed_driver(api, token, created)
    products = seed_products(api, token)
    clients = seed_clients(api, token)
    seed_orders(api, token, clients, products)
    prove_operator(api, created)
    prove_driver(api, driver_pw)

    print("\nCredenciais em:", CRED_FILE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
