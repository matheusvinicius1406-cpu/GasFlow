"""
OPS-01A — matriz de roteamento do nginx de produção (frontend/nginx.conf).

O nginx é a única porta pública da stack `docker-compose.prod.yml`. Este módulo:

1. parseia os `location` blocks do `frontend/nginx.conf`;
2. reimplementa o matcher do nginx (exact > regex na ordem do arquivo >
   prefixo mais longo — ver "Algorithm" da nginx location docs);
3. aplica o `rewrite` de strip `/api` do `location /api`;
4. confere o caminho final enviado ao backend contra as rotas reais do
   FastAPI (`app.openapi()` + `/docs|/redoc|/openapi.json` + `/ws`).

Cobre as regressões do OPS-01A sem precisar de Docker rodando:

- M1: `/api/v1/*` e `/api/driver/*` são servidos COM o prefixo pelo FastAPI
  (strip a partir deles quebrava); `/auth/*`, `/driver/*` (raiz), `/ready` e
  `/payments/webhook/pix` caíam no fallback da SPA (HTML onde se esperava JSON);
- O2: `/metrics` nunca sai pela borda (404 explícito; o Prometheus fala
  direto com backend:8000/whatsapp:3000 na rede interna, com Bearer).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
NGINX_CONF = REPO_ROOT / "frontend" / "nginx.conf"

_LOCATION_RE = re.compile(r"^\s*location\s+(?:(=|~\*|~)\s+)?([^{]+?)\s*\{\s*$")
_REWRITE_RE = re.compile(r"^\s*rewrite\s+(\S+)\s+(\S+)\s+break\s*;", re.MULTILINE)


@dataclass(frozen=True)
class Location:
    """Um `location` block do nginx."""

    modifier: str  # "", "=", "~" ou "~*"
    target: str
    body: str


def parse_locations(text: str) -> list[Location]:
    """Extrai os location blocks mantendo a ordem do arquivo (regex usa ordem)."""
    locations: list[Location] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        match = _LOCATION_RE.match(lines[i])
        if not match:
            i += 1
            continue
        depth = lines[i].count("{") - lines[i].count("}")
        body_lines: list[str] = []
        i += 1
        while i < len(lines) and depth > 0:
            depth += lines[i].count("{") - lines[i].count("}")
            if depth > 0:
                body_lines.append(lines[i])
            i += 1
        locations.append(Location(match.group(1) or "", match.group(2).strip(), "\n".join(body_lines)))
    return locations


def resolve_location(locations: list[Location], uri: str) -> Location:
    """Matcher de location do nginx: exact > regex (ordem) > prefixo mais longo."""
    for loc in locations:
        if loc.modifier == "=" and loc.target == uri:
            return loc
    for loc in locations:
        if loc.modifier in ("~", "~*"):
            flags = 0 if loc.modifier == "~" else re.IGNORECASE
            if re.match(loc.target, uri, flags):
                return loc
    prefixes = [loc for loc in locations if loc.modifier == "" and uri.startswith(loc.target)]
    if not prefixes:
        raise AssertionError(f"nenhum location casa {uri!r}")
    return max(prefixes, key=lambda loc: len(loc.target))


def _upstream_path(loc: Location, uri: str) -> str:
    """Aplica o rewrite do location (strip /api) e devolve o path do backend."""
    match = _REWRITE_RE.search(loc.body)
    if not match:
        return uri
    return re.sub(match.group(1), match.group(2).replace("$1", r"\1"), uri)


def classify(loc: Location, uri: str) -> tuple[str, str | None]:
    """(kind, upstream_path) — kind: proxy | spa | static | 404."""
    if re.search(r"^\s*return\s+404\s*;", loc.body, re.MULTILINE):
        return "404", None
    if "proxy_pass" in loc.body:
        return "proxy", _upstream_path(loc, uri)
    if "try_files" in loc.body:
        if "=404" in loc.body:
            return "static", None
        return "spa", None
    raise AssertionError(f"location {loc.target!r} sem ação reconhecida")


def route(conf: str, uri: str) -> tuple[str, str | None]:
    return classify(resolve_location(parse_locations(conf), uri), uri)


def _iter_routes(routes):
    for route_obj in routes:
        inner = getattr(route_obj, "original_router", None)
        if inner is not None:
            yield from _iter_routes(inner.routes)
        else:
            yield route_obj


@pytest.fixture(scope="module")
def nginx_conf() -> str:
    return NGINX_CONF.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def backend_routes() -> dict[str, set[str]]:
    """path -> {métodos} do FastAPI real (openapi + docs + websocket)."""
    from app.main import app

    spec = app.openapi()
    index: dict[str, set[str]] = {path: {method.upper() for method in ops} for path, ops in spec["paths"].items()}
    for route_obj in _iter_routes(app.routes):
        path = getattr(route_obj, "path", "")
        if path in ("/docs", "/redoc", "/openapi.json"):
            methods = getattr(route_obj, "methods", None) or set()
            index.setdefault(path, set()).update(str(method).upper() for method in methods)
        elif "WebSocket" in type(route_obj).__name__:
            index.setdefault(path, set()).add("WS")
    return index


# ── Matriz URL → destino ────────────────────────────────────────────
# (url, kind, upstream, método esperado no backend)
# kind proxy: upstream é o path que o backend DEVE ter registrado.
# método None: contrato conferido apenas quando a rota existe (docs).
MATRIX: list[tuple[str, str, str | None, str | None]] = [
    # Frontend (axios baseURL /api → strip em `location /api`)
    ("/api/health", "proxy", "/health", "GET"),
    ("/api/clients/", "proxy", "/clients/", "GET"),
    ("/api/orders/", "proxy", "/orders/", "GET"),
    ("/api/auth/login", "proxy", "/auth/login", "POST"),
    ("/api/whatsapp/health", "proxy", "/whatsapp/health", "GET"),
    ("/api/payments/webhook/pix", "proxy", "/payments/webhook/pix", "POST"),
    # FastAPI serve /api/v1/* e /api/driver/* COM o prefixo (sem strip)
    ("/api/v1/health", "proxy", "/api/v1/health", "GET"),
    ("/api/v1/driver/me", "proxy", "/api/v1/driver/me", "GET"),
    ("/api/v1/mobile/version", "proxy", "/api/v1/mobile/version", "GET"),
    ("/api/v1/whatsapp/cloud-api/webhook", "proxy", "/api/v1/whatsapp/cloud-api/webhook", "GET"),
    ("/api/driver/v1/deliveries", "proxy", "/api/driver/v1/deliveries", "GET"),
    # App mobile: rotas raiz do backend (sem /api)
    ("/auth/login", "proxy", "/auth/login", "POST"),
    ("/auth/me", "proxy", "/auth/me", "GET"),
    ("/driver/me", "proxy", "/driver/me", "GET"),
    ("/driver/deliveries", "proxy", "/driver/deliveries", "GET"),
    ("/driver/location", "proxy", "/driver/location", "POST"),
    ("/ws", "proxy", "/ws", "WS"),
    # Post-deploy / webhook PSP
    ("/health", "proxy", "/health", "GET"),
    ("/ready", "proxy", "/ready", "GET"),
    ("/payments/webhook/pix", "proxy", "/payments/webhook/pix", "POST"),
    # O2: métricas nunca pela borda (/metrics, /metrics/ e /api/metrics)
    ("/metrics", "404", None, None),
    ("/metrics/", "404", None, None),
    ("/api/metrics", "404", None, None),
    # SPA: páginas do React Router que colidem com prefixes do backend
    ("/", "spa", None, None),
    ("/driver", "spa", None, None),
    ("/driver/", "spa", None, None),
    ("/driver/login", "spa", None, None),
    ("/track/abc123", "spa", None, None),
    ("/invite/abc123", "spa", None, None),
    # Assets buildados
    ("/assets/index-deadbeef.js", "static", None, None),
]

_PROXY_MATRIX = [row for row in MATRIX if row[1] == "proxy"]


@pytest.mark.parametrize("url,kind,upstream,method", MATRIX)
def test_nginx_route_matrix(nginx_conf: str, url: str, kind: str, upstream: str | None, method: str | None) -> None:
    got_kind, got_upstream = route(nginx_conf, url)
    assert got_kind == kind, f"{url}: esperado {kind}, veio {got_kind}"
    if kind == "proxy":
        assert got_upstream == upstream, f"{url}: backend veria {got_upstream!r}, esperado {upstream!r}"


@pytest.mark.parametrize("url,kind,upstream,method", _PROXY_MATRIX)
def test_upstream_exists_in_backend(
    nginx_conf: str, backend_routes: dict[str, set[str]], url: str, kind: str, upstream: str | None, method: str | None
) -> None:
    """M1: todo caminho enviado ao backend tem rota FastAPI correspondente."""
    assert upstream is not None and method is not None
    assert upstream in backend_routes, f"{url} → {upstream} não existe no FastAPI"
    assert method in backend_routes[upstream], f"{url} → {upstream} sem método {method}"


def test_docs_proxied_when_registered(nginx_conf: str, backend_routes: dict[str, set[str]]) -> None:
    """`/docs|/openapi.json|/redoc` vão ao backend (200 só com DOCS_ENABLED)."""
    for url in ("/docs", "/openapi.json", "/redoc"):
        assert route(nginx_conf, url) == ("proxy", url)
        if url in backend_routes:
            assert "GET" in backend_routes[url]


def test_ws_location_has_upgrade_headers(nginx_conf: str) -> None:
    loc = resolve_location(parse_locations(nginx_conf), "/ws")
    assert loc.target == "/ws"
    assert "proxy_http_version 1.1" in loc.body
    assert "Upgrade $http_upgrade" in loc.body
    assert 'Connection "upgrade"' in loc.body


def test_api_strip_only_in_generic_api_location(nginx_conf: str) -> None:
    """Strip /api só no `location /api`; /api/v1/ e /api/driver/ passam intactos."""
    locations = parse_locations(nginx_conf)
    with_rewrite = [loc.target for loc in locations if _REWRITE_RE.search(loc.body)]
    assert with_rewrite == ["/api"]
    for target in ("/api/v1/", "/api/driver/"):
        loc = next(loc for loc in locations if loc.modifier == "" and loc.target == target)
        assert not _REWRITE_RE.search(loc.body), f"{target} não pode fazer strip"
        assert "proxy_pass http://backend:8000" in loc.body


def test_upload_body_size_on_api_locations(nginx_conf: str) -> None:
    """Import .vcf (≈16 MB) precisa de client_max_body_size nas rotas de upload."""
    locations = parse_locations(nginx_conf)
    for target in ("/api", "/api/v1/", "/api/driver/"):
        loc = next(loc for loc in locations if loc.modifier == "" and loc.target == target)
        assert "client_max_body_size 16m" in loc.body


def test_spa_fallback_is_the_last_location(nginx_conf: str) -> None:
    prefixes = [loc for loc in parse_locations(nginx_conf) if loc.modifier == ""]
    assert prefixes[-1].target == "/"
    assert "try_files $uri $uri/ /index.html" in prefixes[-1].body


def test_metrics_never_proxied(nginx_conf: str) -> None:
    """O2 na borda: nenhuma variação de /metrics chega a um upstream."""
    for url in ("/metrics", "/metrics/", "/metrics/v1", "/api/metrics", "/api/metrics/"):
        assert route(nginx_conf, url) == ("404", None), f"{url} não morreu na borda"
    for loc in parse_locations(nginx_conf):
        if "proxy_pass" not in loc.body:
            continue
        assert not loc.target.startswith("/metrics"), f"location {loc.target} proxia métricas"
        assert not loc.target.startswith("/api/metrics"), f"location {loc.target} proxia métricas"


def test_vite_dev_proxy_keeps_the_same_prefixes() -> None:
    """Paridade dev/prod: o proxy do Vite espelha os prefixes sem strip do nginx."""
    vite = (REPO_ROOT / "frontend" / "vite.config.ts").read_text(encoding="utf-8")
    for prefix in ("'/api/v1'", "'/api/driver'", "'/api'", "'/ws'"):
        assert prefix in vite, f"proxy {prefix} ausente no vite.config.ts"
    assert vite.index("'/api/v1'") < vite.index("'/api'"), "/api/v1 precisa vir antes de /api (match por prefixo)"
    assert vite.index("'/api/driver'") < vite.index("'/api'")
