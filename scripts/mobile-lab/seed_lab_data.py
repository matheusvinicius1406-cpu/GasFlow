#!/usr/bin/env python3
"""MOBILE USB LAB 01 - seed idempotente do laboratorio (somente descartavel).

Cria, EXCLUSIVAMENTE no banco SQLite de laboratorio:

  * tenant ficticio            "GasFlow Laboratorio" (gasflow_lab)
  * admin do tenant            admin_lab
  * entregador ficticio        MOTORISTA-LAB-001 (credencial de lab)
  * 2 produtos ficticios       Gas P13 / Agua 20 L
  * 5 clientes ficticios
  * 5 pedidos + 5 entregas     LAB-001..LAB-005 nos estados do roteiro
  * coordenadas GPS de TESTE   (gravadas direto no banco de lab, rotuladas)

Re-execucao segura: tudo e verificado antes de criar (idempotente) e os IDs
ficam em <lab>/seed-ids.json para repetir os testes sem duplicidade.

NAO envia WhatsApp, NAO emite fiscal, NAO usa dados da Marcos Gas.
As credenciais ficam em <lab>/driver-credentials.txt (FORA do repositorio).

Uso:  python seed_lab_data.py [--api http://127.0.0.1:8010]
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request

LAB_DIR = os.environ.get("GASFLOW_LAB_DIR") or os.path.join(
    os.environ.get("LOCALAPPDATA", "."), "Temp", "opencode", "gasflow-lab"
)
SECRETS = os.path.join(LAB_DIR, "secrets.env")
IDS_FILE = os.path.join(LAB_DIR, "seed-ids.json")
CRED_FILE = os.path.join(LAB_DIR, "driver-credentials.txt")
DB_FILE = os.path.join(LAB_DIR, "gasflow_lab.db")

TENANT_ID = "gasflow_lab"
TENANT_NAME = "GasFlow Laboratorio"
# Documento sintetico do entregador de lab: e a chave de idempotencia do
# cadastro (delivery_drivers.username nao e preenchido pelo use case).
DOCUMENT = "MOTORISTA-LAB-001"

# Coordenadas EXPLICITAMENTE de teste (park/plaza sintetico, nada de endereco real).
TEST_COORDS = [
    (-1.455800, -48.503900),
    (-1.456300, -48.504400),
    (-1.456800, -48.504900),
    (-1.457300, -48.505400),
    (-1.457800, -48.505900),
]

# Roteiro da ETAPA 7: (ref, produto, estado alvo)
PLAN = [
    ("LAB-001", "gas", "PENDING"),
    ("LAB-002", "water", "ASSIGNED"),
    ("LAB-003", "gas", "EN_ROUTE"),
    ("LAB-004", "water", "PENDING"),
    ("LAB-005", "gas", "ASSIGNED"),
]

CLIENTS = [
    ("Cliente Teste Lab 1", "91900000001", "Rua de Teste Lab 1", "10"),
    ("Cliente Teste Lab 2", "91900000002", "Rua de Teste Lab 2", "20"),
    ("Cliente Teste Lab 3", "91900000003", "Rua de Teste Lab 3", "30"),
    ("Cliente Teste Lab 4", "91900000004", "Rua de Teste Lab 4", "40"),
    ("Cliente Teste Lab 5", "91900000005", "Rua de Teste Lab 5", "50"),
]


# ----------------------------------------------------------------- helpers
def load_secrets() -> dict:
    if not os.path.isfile(SECRETS):
        sys.exit(f"[seed] FALTA {SECRETS} - rode start_lab_backend.ps1 primeiro.")
    out = {}
    with open(SECRETS, encoding="ascii") as fh:
        for line in fh:
            if "=" in line:
                k, v = line.rstrip("\n").split("=", 1)
                out[k] = v
    return out


def req(
    method: str,
    path: str,
    payload=None,
    token: str | None = None,
    base: str = "",
    tolerate: tuple = (409,),
    _attempt: int = 0,
) -> dict | list | None:
    url = f"{base}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body.strip() else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        # Rate limit global (5 logins/5 min por IP, 60-120 req/min por rota):
        # espera a janela deslizante liberar e tenta de novo em vez de abortar.
        if exc.code == 429 and _attempt < 5:
            print(
                f"[seed] 429 em {method} {path}: aguardando 60s "
                f"(janela do rate limit) e re-tentando ({_attempt + 1}/5)"
            )
            time.sleep(60)
            return req(method, path, payload, token, base, tolerate, _attempt + 1)
        if exc.code in tolerate or any(
            t in detail.lower()
            for t in ("already exists", "duplicate", "j\\u00e1 existe")
        ):
            return {"__tolerated__": exc.code, "detail": detail}
        raise SystemExit(
            f"[seed] HTTP {exc.code} em {method} {path}: {detail[:400]}"
        ) from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"[seed] Sem resposta de {url}: {exc.reason}") from exc


def login(username: str, password: str, base: str, platform: str = "desktop") -> dict:
    res = req(
        "POST",
        "/auth/login",
        {"username": username, "password": password, "platform": platform},
        base=base,
        tolerate=(),
    )
    if isinstance(res, dict) and (res.get("access_token") or res.get("token")):
        return res
    raise SystemExit(f"[seed] Login recusado para {username}: {json.dumps(res)[:200]}")


def token_of(login_res: dict) -> str:
    return login_res.get("access_token") or login_res.get("token")


def as_list(
    payload, key_candidates=("", "clients", "products", "orders", "deliveries")
) -> list:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in key_candidates:
            if k and isinstance(payload.get(k), list):
                return payload[k]
        for v in payload.values():
            if isinstance(v, list):
                return v
    return []


def save_json(path: str, data: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def load_json(path: str) -> dict:
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


# ----------------------------------------------------------------- etapas
def ensure_tenant(base: str, admin_token: str) -> None:
    tenants = as_list(
        req("GET", "/auth/tenants", token=admin_token, base=base), ("tenants",)
    )
    if any(t.get("tenant_id") == TENANT_ID for t in tenants if isinstance(t, dict)):
        print(f"[seed] tenant '{TENANT_ID}' ja existe")
        return
    res = req(
        "POST",
        "/auth/tenants",
        {"tenant_id": TENANT_ID, "name": TENANT_NAME},
        token=admin_token,
        base=base,
        tolerate=(409, 400),
    )
    print(f"[seed] tenant criado/verificado: {res}")


def ensure_tenant_admin(base: str, admin_token: str, password: str) -> str:
    # Cria PRIMEIRO e so entao loga: o limitador do backend da 5 logins por
    # 5 min por IP, entao cada "login de teste" que falha custa orcamento real.
    res = req(
        "POST",
        "/auth/users",
        {
            "username": "admin_lab",
            "email": "admin_lab@gasflow.lab",
            "password": password,
            "display_name": "Admin Laboratorio",
            "role": "ADMIN",
            "tenant_id": TENANT_ID,
        },
        token=admin_token,
        base=base,
        tolerate=(400, 409),
    )
    if res.get("__tolerated__"):
        print("[seed] tenant admin 'admin_lab' ja existia")
    else:
        print(f"[seed] tenant admin criado: {res}")
    return token_of(login("admin_lab", password, base))


def ensure_product(
    base: str, tok: str, nome: str, tipo: str, preco: float, estoque: int
) -> str:
    for p in as_list(req("GET", "/products/", token=tok, base=base), ("products",)):
        if isinstance(p, dict) and p.get("nome") == nome:
            return str(p.get("codigo"))
    res = req(
        "POST",
        "/products/",
        {"nome": nome, "tipo": tipo, "preco": preco, "estoque": estoque},
        token=tok,
        base=base,
        tolerate=(409,),
    )
    codigo = str(res.get("codigo") or res.get("product", {}).get("codigo"))
    print(f"[seed] produto criado: {nome} -> {codigo}")
    return codigo


def ensure_stock(base: str, tok: str, product_codigo: str, target: int = 100) -> None:
    """Garante estoque via API real de movimentacao.

    CreateOrderUseCase le Inventory.quantity (FASE 7.1) e IGNORA
    products.estoque, entao um produto recem-criado nao e vendivel ate
    haver linha/movimento em `inventory`. Entrada feita pela rota real
    /inventory/{codigo}/entries, nunca por UPDATE direto.
    """
    res = req(
        "GET", f"/inventory/{product_codigo}", token=tok, base=base, tolerate=(404,)
    )
    inv = res.get("inventory") if isinstance(res, dict) else None
    current = int((inv or {}).get("quantity") or 0)
    if current >= target:
        print(f"[seed] estoque do produto {product_codigo}: {current} (ja suficiente)")
        return
    req(
        "POST",
        f"/inventory/{product_codigo}/entries",
        {
            "quantity": target - current,
            "reason": "Entrada de estoque de LABORATORIO (sintetica)",
        },
        token=tok,
        base=base,
        tolerate=(),
    )
    print(f"[seed] estoque do produto {product_codigo}: {current} -> {target}")


def ensure_client(
    base: str, tok: str, nome: str, telefone: str, rua: str, numero: str
) -> str:
    for c in as_list(req("GET", "/clients/", token=tok, base=base), ("clients",)):
        if isinstance(c, dict) and c.get("nome") == nome:
            return str(c.get("codigo"))
    res = req(
        "POST",
        "/clients/",
        {
            "nome": nome,
            "telefone": telefone,
            "rua": rua,
            "numero": numero,
            "bairro": "Bairro Laboratorio",
            "complemento": "TESTE-LAB",
            "referencia": "Ponto sintetico de teste - nao e endereco real",
        },
        token=tok,
        base=base,
        tolerate=(409,),
    )
    codigo = str(res.get("codigo") or res.get("client", {}).get("codigo"))
    print(f"[seed] cliente ficticio criado: {nome} -> {codigo}")
    return codigo


def ensure_order(
    base: str,
    tok: str,
    client_codigo: str,
    product_codigo: str,
    qty: int,
    key: str,
    store: dict,
) -> str:
    if key in store:
        try:
            req("GET", f"/orders/{store[key]}", token=tok, base=base, tolerate=())
            return store[key]
        except SystemExit:
            print(f"[seed] pedido {key} nao existe mais; recriando")
    res = req(
        "POST",
        "/orders/",
        {
            "client_codigo": client_codigo,
            "items": [{"product_codigo": product_codigo, "quantity": qty}],
            "delivery_fee": 0.0,
            "discount": 0.0,
            "payment_method": "PIX",
            "source": "MANUAL",
            "notes": f"PEDIDO DE LABORATORIO {key} - sintetico",
        },
        token=tok,
        base=base,
        tolerate=(),
    )
    codigo = str(
        res.get("codigo") or res.get("order", {}).get("codigo") or res.get("id")
    )
    if not codigo:
        raise SystemExit(
            f"[seed] resposta de pedido sem codigo: {json.dumps(res)[:300]}"
        )
    print(f"[seed] pedido criado: {key} -> {codigo}")
    return codigo


def ensure_delivery(
    base: str,
    tok: str,
    order_id: str,
    ref: str,
    client_codigo: str,
    client_nome: str,
    rua: str,
    numero: str,
    store: dict,
) -> str:
    if ref in store:
        try:
            req(
                "GET",
                f"/delivery/deliveries/{store[ref]}",
                token=tok,
                base=base,
                tolerate=(),
            )
            return store[ref]
        except SystemExit:
            print(f"[seed] entrega {ref} nao existe mais; recriando")
    res = req(
        "POST",
        "/delivery/deliveries",
        {
            "order_id": order_id,
            "customer_codigo": client_codigo,
            "customer_name": client_nome,
            "address": {
                "street": rua,
                "number": numero,
                "complement": "TESTE-LAB",
                "neighborhood": "Bairro Laboratorio",
                "city": "Belem",
                "state": "PA",
                "zip_code": "66000-000",
                "reference": "ENDERECO SINTECO DE TESTE - nao representa entrega real",
            },
            "notes": f"{ref} | ENTREGA DE LABORATORIO - dados 100% sinteticos",
        },
        token=tok,
        base=base,
        tolerate=(),
    )
    did = str(res.get("delivery", {}).get("id") or res.get("id"))
    if not did:
        raise SystemExit(f"[seed] resposta de entrega sem id: {json.dumps(res)[:300]}")
    print(f"[seed] entrega criada: {ref} -> {did}")
    return did


def delivery_status(base: str, tok: str, did: str) -> str:
    res = req("GET", f"/delivery/deliveries/{did}", token=tok, base=base, tolerate=())
    return str((res.get("delivery") or res).get("status", ""))


def ensure_state(
    base: str, tok: str, did: str, target: str, driver_codigo: str
) -> None:
    cur = delivery_status(base, tok, did)
    if cur == target:
        print(f"[seed] {did}: ja em {target}")
        return
    if target == "PENDING":
        print(
            f"[seed] {did}: PENDING nao transiciona via API (estado inicial) - atual {cur}"
        )
        return
    if cur == "PENDING":
        res = req(
            "PATCH",
            f"/delivery/deliveries/{did}/assign",
            {"driver_id": driver_codigo},
            token=tok,
            base=base,
            tolerate=(),
        )
        if res.get("__tolerated__"):
            print(f"[seed] {did}: assign ja havia acontecido ({res['detail'][:80]})")
        cur = delivery_status(base, tok, did)
    if cur == target:
        print(f"[seed] {did}: -> {target}")
        return
    if target == "ASSIGNED" and cur != "ASSIGNED":
        raise SystemExit(f"[seed] {did}: impossivel chegar em ASSIGNED (atual {cur})")
    res = req(
        "PATCH",
        f"/delivery/deliveries/{did}/status",
        {"status": target},
        token=tok,
        base=base,
        tolerate=(),
    )
    if res.get("__tolerated__"):
        print(f"[seed] {did}: status {target} ja aplicado ({res['detail'][:80]})")
    else:
        print(f"[seed] {did}: -> {target}")


def ensure_driver(
    base: str, lab_admin_token: str, username: str, password: str
) -> tuple[str, dict, str]:
    """Retorna (codigo_do_motorista, credencial_final, token_da_sessao).

    O token e devolvido para que o chamador nao precise de outro POST
    /auth/login: o limitador do backend da 5 logins por 5 min por IP e cada
    login extra queima orcamento de todos os scripts da sequencia.
    """
    # 1) existe? lista com token de admin - nao gasta orcamento de login.
    # A chave NAO e so o username: CreateDriverWithCredentialUseCase grava o
    # username apenas em auth_users; delivery_drivers.username fica NULL.
    # O document (MOTORISTA-LAB-001) e o unico campo estavel na entidade.
    creds = {"username": username, "password": password}
    existing: dict[str, str] = {}
    for d in as_list(
        req("GET", "/delivery/drivers", token=lab_admin_token, base=base),
        ("drivers",),
    ):
        if not isinstance(d, dict):
            continue
        codigo = str(d.get("codigo") or "")
        if d.get("username"):
            existing[str(d["username"])] = codigo
        if d.get("document"):
            existing[str(d["document"])] = codigo

    if username in existing or DOCUMENT in existing:
        codigo = existing.get(username) or existing.get(DOCUMENT) or ""
        try:
            lg = login(username, password, base, platform="mobile")
        except SystemExit:
            raise SystemExit(
                "[seed] entregador existe mas a senha de lab nao funciona. "
                "Recrie o laboratorio (apague o banco de lab) ou troque a senha manualmente."
            ) from None
        print(f"[seed] entregador '{username}' ja ativo com credencial de lab")
        info = req("GET", "/driver/me", token=token_of(lg), base=base, tolerate=())
        codigo = str(
            info.get("codigo") or info.get("driver_id") or info.get("id") or codigo
        )
        return codigo, creds, token_of(lg)

    # 2) nao existe: cria e troca a senha temporaria (2 logins, so na 1a execucao)
    res = req(
        "POST",
        "/admin/drivers",
        {
            "name": "Entregador Teste",
            "phone": "91900000099",
            "document": DOCUMENT,
            "username": username,
        },
        token=lab_admin_token,
        base=base,
        tolerate=(409,),
    )
    if res.get("__tolerated__"):
        raise SystemExit(
            f"[seed] driver existente com outro dono: {res['detail'][:200]}"
        )
    codigo = str(res.get("driver_id") or res.get("driver", {}).get("codigo"))
    temp_pw = res.get("temporary_password")
    print(f"[seed] entregador criado: codigo={codigo} usuario={username}")

    lg = login(username, temp_pw, base, platform="mobile")
    req(
        "POST",
        "/auth/change-password",
        {"current_password": temp_pw, "new_password": password},
        token=token_of(lg),
        base=base,
        tolerate=(),
    )
    print("[seed] senha temporaria trocada pela senha de laboratorio")
    lg = login(username, password, base, platform="mobile")
    return codigo, creds, token_of(lg)


def patch_test_coordinates(store: dict) -> None:
    """Grava lat/lng de TESTE e associa as entregas PENDING ao motorista.

    Feito direto no SQLite de laboratorio porque a API HTTP nao aceita lat/lng
    (AddressSchema nao expoe o campo) e nao ha endpoint de assign que preserve
    PENDING. Somente no banco descartavel de lab - nunca no operacional.
    """
    if not os.path.isfile(DB_FILE):
        print(f"[seed] AVISO: banco {DB_FILE} nao encontrado; pulando coordenadas")
        return
    con = sqlite3.connect(DB_FILE, timeout=15)
    try:
        con.execute("PRAGMA journal_mode=WAL")
        driver = store.get("driver", {}).get("codigo")
        updated = 0
        for i, ref in enumerate([p[0] for p in PLAN]):
            did = store.get("deliveries", {}).get(ref)
            if not did:
                continue
            lat, lng = TEST_COORDS[i]
            cur = con.execute(
                "UPDATE delivery_records SET address_lat=?, address_lng=?, "
                "driver_id = COALESCE(driver_id, ?) WHERE delivery_id=?",
                (lat, lng, driver, did),
            )
            updated += cur.rowcount
            con.commit()
        if updated == 0:
            # Falhar ruidosamente e melhor que "sucesso" silencioso: a ultima
            # vez o WHERE usava a PK integer com o UUID - 0 linhas, tudo falso.
            raise SystemExit(
                "[seed] FALHA: nenhuma delivery_records atualizada "
                "(chave do WHERE nao bate com delivery_id)"
            )
        print(
            f"[seed] coordenadas GPS de TESTE gravadas em {updated} entregas "
            "(address_lat/lng) e PENDING associadas ao motorista"
        )
    finally:
        con.close()


# ----------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description="Seed idempotente do laboratorio GasFlow")
    ap.add_argument("--api", default="http://127.0.0.1:8010")
    args = ap.parse_args()
    base = args.api.rstrip("/")

    secrets = load_secrets()
    store = load_json(IDS_FILE)
    store.setdefault("deliveries", {})
    store.setdefault("orders", {})

    health = req("GET", "/health", base=base, tolerate=())
    print(f"[seed] saude do backend: {health}")

    # 1-2. tenant + admin do tenant (contexto de tenant necessario para criar entregas)
    adm = login("admin", secrets["ADMIN_PASSWORD"], base)
    ensure_tenant(base, token_of(adm))
    lab_tok = ensure_tenant_admin(base, token_of(adm), secrets["LAB_TENANT_ADMIN_PW"])

    # 3-4. produtos e clientes ficticios
    prod_gas = ensure_product(base, lab_tok, "Gas P13", "GAS", 120.0, 100)
    prod_water = ensure_product(base, lab_tok, "Agua 20 L", "AGUA", 10.0, 100)
    ensure_stock(base, lab_tok, prod_gas, 100)
    ensure_stock(base, lab_tok, prod_water, 100)

    client_codes = []
    for nome, tel, rua, numero in CLIENTS:
        client_codes.append(ensure_client(base, lab_tok, nome, tel, rua, numero))

    # 5. entregador (credencial util)
    driver_codigo, creds, drv_token = ensure_driver(
        base, lab_tok, secrets["LAB_DRIVER_USERNAME"], secrets["LAB_DRIVER_PASSWORD"]
    )
    store["driver"] = {"codigo": driver_codigo, "username": creds["username"]}
    with open(CRED_FILE, "w", encoding="ascii") as fh:
        fh.write("GasFlow - credenciais de LABORATORIO (nao usar em producao)\n")
        fh.write(f"Servidor : {base}\n")
        fh.write(f"Tenant   : {TENANT_ID} ({TENANT_NAME})\n")
        fh.write(f"Usuario  : {creds['username']}\n")
        fh.write(f"Senha    : {creds['password']}\n")
        fh.write(f"Documento/Motorista: {DOCUMENT}\n")
    os.chmod(CRED_FILE, 0o600) if os.name != "nt" else None
    print(f"[seed] credencial de lab gravada em {CRED_FILE}")

    # 6. pedidos + entregas no estado do roteiro
    for i, (ref, which, target) in enumerate(PLAN):
        prod = prod_gas if which == "gas" else prod_water
        client_nome, _tel, rua, numero = CLIENTS[i]
        order_id = ensure_order(
            base, lab_tok, client_codes[i], prod, 1, ref, store["orders"]
        )
        store["orders"][ref] = order_id
        did = ensure_delivery(
            base,
            lab_tok,
            order_id,
            ref,
            client_codes[i],
            client_nome,
            rua,
            numero,
            store["deliveries"],
        )
        store["deliveries"][ref] = did
        if driver_codigo:
            ensure_state(base, lab_tok, did, target, driver_codigo)

    save_json(IDS_FILE, store)
    patch_test_coordinates(store)

    # verificacao final pelo olho do entregador (reusa o token - nao faz login novo)
    mine = as_list(
        req(
            "GET",
            "/driver/deliveries",
            token=drv_token,
            base=base,
            tolerate=(),
        ),
        ("deliveries",),
    )
    print(f"\n[seed] ENTREGAS VISIVEIS AO ENTREGADOR: {len(mine)}")
    for d in sorted(mine, key=lambda x: str(x.get("id"))):
        note = str(d.get("notes") or "").split("|")[0].strip()
        print(
            f"   {note or d.get('id')}: status={d.get('status')} "
            f"lat={d.get('address', {}).get('lat')} lng={d.get('address', {}).get('lng')}"
        )
    print(f"[seed] IDs gravados em {IDS_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
