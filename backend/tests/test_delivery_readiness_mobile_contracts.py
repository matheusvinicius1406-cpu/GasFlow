"""Readiness de entrega — contratos do app do entregador ↔ backend ↔ Home Server.

Objetivo (frente QA/readiness, sem novas features): provar, de forma estática e
com TestClient em banco efêmero, que os contratos que o app Android usa de fato
existem no backend e continuam protegidos. Não duplica os testes de
comportamento já existentes (`test_driver_self_actions`, `test_driver_mobile`,
`test_driver_location_ingest`, `test_mobile_version`, `test_public_tracking`):
o foco aqui é a **costura entre as duas pontas** + o que o Home Server expõe.

Coberto:

- toda URL montada em `mobile/src/logic/api.ts` existe no OpenAPI com o método
  certo (e a lista de namespaces usados pelo app está congelada — um hardcode
  novo quebra o teste);
- `/driver/*` e `/auth/*` respondem 401 sem token e `/driver/me` recusa
  operador/admin com 403 (matriz sobre todas as rotas do app);
- WebSocket `/ws` recusa token inválido (4001) — canal do realtime do app;
- payload de `/api/v1/mobile/version` cobre a interface `MobileVersionInfo` do
  app (update OTA do APK);
- `/public/tracking/{token}` devolve somente posição (sem PII), por construção;
- nenhum IP privado hardcoded no app além dos defaults de dev
  (`10.0.2.2`, `127.0.0.1`);
- as lacunas de contrato conhecidas (idempotência, `arrive`, telefone,
  `failure_reason`) seguem documentadas em `docs/delivery/`.

Fora de escopo (não executado aqui): Android físico, GPS real, Docker/Nginx
reais, câmera/assinatura, WhatsApp real.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app
from app.presentation.api.logistics.driver_api import ActionRequest

REPO_ROOT = Path(__file__).resolve().parents[2]
MOBILE_SRC = REPO_ROOT / "mobile" / "src"
API_TS = MOBILE_SRC / "logic" / "api.ts"
UPDATE_TS = MOBILE_SRC / "logic" / "mobileUpdate.ts"
LOGIN_SCREEN = MOBILE_SRC / "screens" / "LoginScreen.tsx"
PUBLIC_TRACKING = REPO_ROOT / "backend" / "app" / "presentation" / "api" / "public_tracking.py"
DELIVERY_MODEL = REPO_ROOT / "backend" / "app" / "infrastructure" / "repositories" / "delivery_persistence_model.py"
DELIVERY_DOC = REPO_ROOT / "docs" / "delivery" / "PENDENCIAS_BLOQUEANTES.md"
STATUS_DOC = REPO_ROOT / "docs" / "delivery" / "STATUS_DE_ENTREGA.md"
DEMO_DOC = REPO_ROOT / "docs" / "delivery" / "ROTEIRO_DEMO.md"

# Namespaces que o app pode chamar no Home Server. `/api/v1/mobile/version` é a
# única rota com prefixo `/api` (nginx encaminha sem strip) e `/ws` é o canal.
EXPECTED_MOBILE_CALLS = {
    ("POST", "/auth/login"),
    ("GET", "/auth/me"),
    ("POST", "/auth/change-password"),
    ("GET", "/driver/deliveries"),
    ("GET", "/driver/me"),
    ("POST", "/driver/deliveries/{}/accept"),
    ("POST", "/driver/deliveries/{}/start"),
    ("POST", "/driver/deliveries/{}/complete"),
    ("POST", "/driver/deliveries/{}/fail"),
    ("POST", "/driver/location"),
}

# Corpo mínimo válido para chegar na dependência de auth (e receber 401).
MINIMAL_BODY = {
    "/auth/login": {"username": "x", "password": "y"},
    "/auth/change-password": {"current_password": "a", "new_password": "b"},
    "/driver/location": {"latitude": 0.0, "longitude": 0.0},
    "/driver/deliveries/{}/accept": {},
    "/driver/deliveries/{}/start": {},
    "/driver/deliveries/{}/complete": {},
    "/driver/deliveries/{}/fail": {"failure_reason": "OTHER"},
}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def _read(path: Path) -> str:
    assert path.exists(), f"{path.name} ausente"
    return path.read_text(encoding="utf-8")


def _canonical(path: str) -> str:
    """`/driver/deliveries/${id}/start` → `/driver/deliveries/{}/start`."""
    normalized = re.sub(r"\$\{[^}]+\}", "{}", path.rstrip("/"))
    return re.sub(r"\{[^}]+\}", "{}", normalized)


def _mobile_calls() -> set[tuple[str, str]]:
    """Extrai (método, path) das URLs que o app monta com a base do backend."""
    text = _read(API_TS)
    template = re.compile(r"`\$\{[^}]+\}((?:/[\w\-.${}]+)+)`")
    calls: set[tuple[str, str]] = set()
    for match in template.finditer(text):
        # Janela = função inteira que monta a URL (o `method` pode vir depois
        # de vários ternários, como em postDeliveryAction).
        start = text.rfind("export async function", 0, match.start())
        end = text.find("export async function", match.end())
        window = text[start if start >= 0 else 0 : end if end >= 0 else len(text)]
        method = "POST" if re.search(r'method:\s*"POST"', window) else "GET"
        calls.add((method, _canonical(match.group(1))))
    return calls


def _interface_fields(path: Path, name: str) -> set[str]:
    block = re.search(rf"interface {name} \{{(.*?)\n\}}", _read(path), re.S)
    assert block, f"interface {name} não encontrada em {path.name}"
    return set(re.findall(r"^\s*(\w+)\??:", block.group(1), re.M))


def _openapi_methods() -> dict[str, set[str]]:
    spec = app.openapi()
    return {path: {method.upper() for method in operations} for path, operations in spec["paths"].items()}


# ── Contrato de rotas ────────────────────────────────────────────


def test_every_mobile_call_exists_in_openapi() -> None:
    methods = _openapi_methods()
    canonical = {_canonical(path): verbs for path, verbs in methods.items()}
    missing = [
        (method, path) for method, path in _mobile_calls() if path not in canonical or method not in canonical[path]
    ]
    assert not missing, f"app chama rotas que o backend não expõe: {missing}"


def test_mobile_call_inventory_is_frozen() -> None:
    """Qualquer URL nova/removida no app precisa passar por este inventário."""
    assert _mobile_calls() == EXPECTED_MOBILE_CALLS


def test_websocket_channel_rejects_invalid_token(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws?token=not-a-real-token"):
            pass
    assert excinfo.value.code == 4001, "token inválido deve fechar com 4001 (o app reconecta/desiste)"


# ── Auth: 401 sem token, 403 para quem não é entregador ──────────


def test_mobile_routes_require_bearer_token(client: TestClient) -> None:
    unauthenticated = []
    for method, path in sorted(_mobile_calls()):
        if not path.startswith(("/driver/", "/auth/")) or path == "/auth/login":
            continue
        url = path.replace("{}", "readiness-does-not-exist")
        kwargs: dict = {"json": MINIMAL_BODY.get(path, {})} if method == "POST" else {}
        response = client.request(method, url, **kwargs)
        if response.status_code != 401:
            unauthenticated.append((method, url, response.status_code))
    assert not unauthenticated, f"rotas do app acessíveis sem token: {unauthenticated}"


def test_driver_profile_rejects_non_driver_role(client: TestClient) -> None:
    login = client.post(
        "/auth/login",
        json={"username": "admin", "password": "test_password_123"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["token"]
    response = client.get("/driver/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403, "admin não pode consumir o namespace do entregador"


# ── Update OTA do APK ────────────────────────────────────────────


def test_mobile_version_payload_covers_app_interface(client: TestClient) -> None:
    response = client.get("/api/v1/mobile/version")
    assert response.status_code == 200, response.text
    payload = response.json()
    expected = _interface_fields(UPDATE_TS, "MobileVersionInfo")
    missing = sorted(field for field in expected if field not in payload)
    assert not missing, f"app espera campos ausentes no /api/v1/mobile/version: {missing}"
    assert payload["latest_version"] and payload["download_url"] is not None


# ── Rastreio público sem PII ────────────────────────────────────


def test_public_tracking_snapshot_returns_position_only() -> None:
    text = _read(PUBLIC_TRACKING)
    snapshot = re.search(r"async def public_tracking_snapshot.*?return \{(.*?)\n        \}", text, re.S)
    assert snapshot, "handler do rastreio público não encontrado"
    keys = set(re.findall(r'"(\w+)":', snapshot.group(1)))
    assert keys == {"driver_id", "latitude", "longitude", "updated_at"}, keys
    forbidden = {"phone", "address", "customer_name", "customer_phone", "notes"}
    assert not (keys & forbidden), "rastreio público não pode expor PII"


# ── Higiene da configuração do app ──────────────────────────────


def test_mobile_sources_have_no_hardcoded_private_hosts() -> None:
    allowed = {"10.0.2.2", "127.0.0.1"}
    offenders = []
    for path in MOBILE_SRC.rglob("*"):
        if path.suffix not in {".ts", ".tsx"} or not path.is_file():
            continue
        for number, line in enumerate(_read(path).splitlines(), start=1):
            if line.strip().startswith(("*", "//", "/*")):
                continue  # comentário/exemplo de docstring não é configuração
            for ip in re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", line):
                if ip not in allowed:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{number} -> {ip}")
    assert not offenders, f"IP hardcoded no app (vaza endereço do servidor): {offenders}"


def test_home_server_url_guidance_is_documented() -> None:
    demo = _read(DEMO_DOC)
    status = _read(STATUS_DOC)
    assert "http://<ip>" in demo and "sem `:8000`" in demo, "demo precisa ensinar a URL do Home Server (porta 80)"
    assert "8000" in status, "status precisa registrar a incompatibilidade de :8000 com o Home Server"
    assert "http://ip:8000" in _read(LOGIN_SCREEN), (
        "placeholder do app mudou: revisar a orientação de URL e o relatório de entrega"
    )


# ── Lacunas de contrato conhecidas (documentadas, não corrigidas) ──


def test_known_mobile_contract_gaps_are_documented() -> None:
    doc = _read(DELIVERY_DOC)
    for token in ("client_action_id", "idempotency_key", "/arrive", "failure_reason", "phone"):
        assert token in doc, f"lacuna {token!r} sem registro em PENDENCIAS_BLOQUEANTES.md"

    # Fatos do código que sustentam a documentação (se mudarem, revisar o doc).
    assert "client_action_id" not in ActionRequest.model_fields
    assert "idempotency_key" in ActionRequest.model_fields
    assert "arrive" not in _read(API_TS), "app passou a chamar /arrive: atualizar demo e pendências"
    assert "phone" not in re.findall(
        r'"(\w+)":',
        re.search(r"def to_dict.*?return \{(.*?)\n        \}", _read(DELIVERY_MODEL), re.S).group(1),
    ), "backend passou a enviar phone: atualizar pendências"
