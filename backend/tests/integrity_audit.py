"""Auditoria de integridade do app GasFlow — guard de CI.

Cruza o que existe em cada superfície para garantir que nada fique órfão:
quebrado (tela sem endpoint / botão sem handler), perdido (rota sem link /
feature fantasma) ou sem conexão (backend órfão / dado invisível).

Superfícies cobertas: frontend web, backend, desktop (IPC), WhatsApp, mobile.

Uso:
    python -m tests.integrity_audit            # imprime o resumo dos findings
    python -m tests.integrity_audit --report   # também grava JSON + Markdown

O teste `tests/test_app_integrity.py` roda as mesmas checagens e falha se
houver finding fora da allowlist (`tests/integrity_allowlist.json`).
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
FRONTEND = REPO / "frontend" / "src"
DESKTOP = REPO / "desktop" / "src"
WHATSAPP = REPO / "whatsapp" / "src"
MOBILE = REPO / "mobile" / "src"
ALLOWLIST = BACKEND / "tests" / "integrity_allowlist.json"
REPORT_DIR = REPO / "docs" / "auditoria" / "integridade"

# Prefixos que o mesmo router ganha em montagens diferentes (raiz, /api/v1,
# mirror /api no FRONTEND_DIST). Normalizar por eles permite comparar a chamada
# do front (baseURL '/api') com a rota canônica do OpenAPI.
API_PREFIXES = ("/api/v1", "/api/driver/v1", "/driver/v1", "/api")

_SKIP_PARTS = {"node_modules", "dist", "build", "coverage", "__pycache__"}


@dataclass(frozen=True)
class Finding:
    """Um problema de integridade: `check` + `target` identificam a allowlist."""

    check: str
    target: str
    detail: str


# ── Utilidades ────────────────────────────────────────────────────────────


def _files(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    if not root.is_dir():
        return []
    return [
        p for p in sorted(root.rglob("*")) if p.is_file() and p.suffix in suffixes and not (_SKIP_PARTS & set(p.parts))
    ]


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _is_test(path: Path) -> bool:
    name = path.name
    return ".test." in name or name.startswith("test_") or name.endswith("_test.py")


# Params: {id} (FastAPI), ${id} (template JS) e :id (Express/React Router).
_PARAM_RE = re.compile(r"\{[^}]*\}|\$\{[^}]*\}|:[A-Za-z_]\w*")


def normalize_path(path: str) -> str:
    """Uniformiza rota/caminho: remove query, achata params e a barra final."""
    path = path.split("?")[0].split("#")[0]
    path = _PARAM_RE.sub("*", path.strip())
    path = re.sub(r"/{2,}", "/", path)
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    if path and not path.startswith("/"):
        path = "/" + path
    return path or "/"


def strip_prefix(path: str) -> str:
    for prefix in API_PREFIXES:
        if path == prefix:
            return "/"
        if path.startswith(prefix + "/"):
            return path[len(prefix) :]
    return path


# ── Coletores: frontend ───────────────────────────────────────────────────

_ROUTE_RE = re.compile(r'<Route\s+path="([^"]*)"')
_HREF_RE = re.compile(r"""href:\s*'([^']+)'""")
_TO_RE = re.compile(r"""(?:to|href)\s*=\s*["'`]([^"'`]+)""")
_NAVIGATE_RE = re.compile(r"""navigate\(\s*["'`]([^"'`]+)""")
_API_CALL_RE = re.compile(r"""apiClient\.(get|post|put|patch|delete)\(\s*(`[^`]*`|'[^']*'|"[^"]*")""")


def frontend_routes() -> set[str]:
    """Toda rota declarada em App.tsx (aninhadas viram caminho absoluto)."""
    routes: set[str] = {"/"}
    for raw in _ROUTE_RE.findall(_read(FRONTEND / "App.tsx")):
        raw = raw.strip()
        if not raw:
            continue
        routes.add(normalize_path(raw if raw.startswith("/") else "/" + raw))
    return routes


def nav_hrefs() -> set[str]:
    return {normalize_path(h) for h in _HREF_RE.findall(_read(FRONTEND / "components" / "layout" / "nav.tsx"))}


def link_targets() -> dict[str, set[str]]:
    """Alvos de `<Link to>` / `navigate()` por arquivo (só caminhos internos)."""
    out: dict[str, set[str]] = {}
    for path in _files(FRONTEND, (".tsx", ".ts")):
        found = {normalize_path(v) for v in _TO_RE.findall(_read(path)) if v.startswith("/")}
        found |= {normalize_path(v) for v in _NAVIGATE_RE.findall(_read(path)) if v.startswith("/")}
        if found:
            out[str(path.relative_to(FRONTEND))] = found
    return out


def frontend_api_calls() -> list[tuple[str, str, str]]:
    """(arquivo, método, caminho) de toda chamada feita via apiClient."""
    calls: list[tuple[str, str, str]] = []
    for path in _files(FRONTEND, (".ts", ".tsx")):
        if _is_test(path):
            continue
        for method, literal in _API_CALL_RE.findall(_read(path)):
            raw = literal[1:-1]
            if raw.startswith("/"):
                calls.append((str(path.relative_to(FRONTEND)), method.upper(), normalize_path(raw)))
    return calls


# ── Coletor: backend ──────────────────────────────────────────────────────


def websocket_routes() -> set[str]:
    """Caminhos de WebSocket da app — o OpenAPI não os expõe.

    Nesta versão do FastAPI os routers incluídos ficam aninhados em
    `_IncludedRouter` (cada nível guardando o próprio prefixo), então a
    coleta desce a árvore manualmente.
    """
    from fastapi.routing import APIWebSocketRoute, _IncludedRouter

    from app.main import app

    paths: set[str] = set()

    def walk(routes, prefix: str) -> None:
        for route in routes:
            if isinstance(route, _IncludedRouter):
                walk(route.original_router.routes, prefix + route.include_context.prefix)
            elif isinstance(route, APIWebSocketRoute):
                paths.add(prefix + route.path)
            elif getattr(route, "routes", None):
                walk(route.routes, prefix)

    walk(app.routes, "")
    return paths


def backend_routes() -> set[str]:
    """Rotas canônicas do FastAPI (OpenAPI + WebSocket), raiz e sem prefixo.

    WebSocket entra junto porque o app mobile abre `ws://host/ws`; sem ele o
    guard acusaria endpoint inexistente para uma rota que existe.
    """
    from app.main import app

    paths = set(app.openapi().get("paths", {})) | websocket_routes()

    routes: set[str] = set()
    for path in paths:
        normalized = normalize_path(path)
        routes.add(normalized)
        routes.add(normalize_path(strip_prefix(normalized)))
    return routes


# ── Coletores: desktop ────────────────────────────────────────────────────

_PRELOAD_INVOKE_RE = re.compile(
    r'(\w+):\s*(?:\([^)]*\)|\w+)\s*=>\s*electron_1\.ipcRenderer\.(?:invoke|send)\(\s*"([^"]+)"'
)
_PRELOAD_SUBSCRIBE_RE = re.compile(r'(\w+):\s*\([^)]*\)\s*=>\s*subscribe\(\s*"([^"]+)"')
_MAIN_HANDLER_RE = re.compile(r'ipcMain\.(?:handle|on)\(\s*"([^"]+)"')
# No bundle transpilado o helper aparece como
# `(0, ipc_permissions_1.registerProtectedHandler)("canal", ...)`.
_MAIN_PROTECTED_RE = re.compile(r'registerProtectedHandler[^"]{0,6}"([^"]+)"')
_MAIN_SEND_RE = re.compile(r'\.send\(\s*"([^"]+)"')


def _code_only(src: str) -> str:
    """Remove linhas que são só comentário — evita casar exemplos em docstring."""
    return "\n".join(line for line in src.splitlines() if not line.lstrip().startswith(("*", "//", "/*")))


def desktop_preload() -> dict[str, tuple[str, str]]:
    """Método do bridge -> (canal, tipo), tipo em {'invoke', 'event'}.

    `invoke` precisa de `ipcMain.handle`; `event` é main→renderer e precisa de
    um emissor (`webContents.send`), não de handler.
    """
    src = _read(DESKTOP / "preload" / "index.ts")
    methods = {m: (c, "invoke") for m, c in _PRELOAD_INVOKE_RE.findall(src)}
    methods.update({m: (c, "event") for m, c in _PRELOAD_SUBSCRIBE_RE.findall(src)})
    return methods


def desktop_handlers() -> set[str]:
    channels: set[str] = set()
    for path in _files(DESKTOP / "main", (".ts",)):
        src = _code_only(_read(path))
        channels |= set(_MAIN_HANDLER_RE.findall(src))
        channels |= set(_MAIN_PROTECTED_RE.findall(src))
    return channels


def desktop_emitted() -> set[str]:
    """Canais que o main emite para o renderer (webContents.send)."""
    emitted: set[str] = set()
    for path in _files(DESKTOP / "main", (".ts",)):
        emitted |= set(_MAIN_SEND_RE.findall(_code_only(_read(path))))
    return emitted


def renderer_source_text() -> str:
    """Fontes do renderer vivo (React) — sem testes, que mockam a ponte."""
    return _source_text(FRONTEND)


def renderer_uses(method: str, text: str) -> bool:
    """Teste conservador: o método aparece pelo nome em qualquer lugar do renderer."""
    return re.search(rf"\b{re.escape(method)}\b", text) is not None


# ── Coletor: WhatsApp ─────────────────────────────────────────────────────

_WA_ROUTE_RE = re.compile(r"""router\.(get|post|put|patch|delete)\(\s*['"]([^'"]+)['"]""")


def whatsapp_routes() -> set[str]:
    src = _read(WHATSAPP / "routes.ts")
    return {normalize_path(p) for _, p in _WA_ROUTE_RE.findall(src)}


def _source_text(*roots: Path) -> str:
    """Concatena o conteúdo-fonte das árvores indicadas."""
    chunks: list[str] = []
    for root in roots:
        for path in _files(root, (".ts", ".tsx", ".py", ".js")):
            chunks.append(_read(path))
    return "\n".join(chunks)


def _consumer_text() -> str:
    """Todo o código consumidor (fora do próprio serviço WhatsApp)."""
    return _source_text(BACKEND / "app", FRONTEND, DESKTOP, REPO / "agent" / "src", MOBILE)


def _route_regex(route: str) -> re.Pattern[str]:
    """Rota com params vira regex que casa com valores concretos do consumidor."""
    return re.compile(re.escape(route).replace(r"\*", r"[^/\s\"'`]*"))


# ── Coletor: mobile ───────────────────────────────────────────────────────

# Qualquer template de URL em api.ts: `${...}` + caminho literal.
_MOBILE_URL_RE = re.compile(r"`\$\{[^}]+\}([^`]*)`")
_MOBILE_SCREEN_RE = re.compile(r"""<Stack\.Screen\s+name="([^"]+)""")


def mobile_api_paths() -> set[str]:
    found = _MOBILE_URL_RE.findall(_read(MOBILE / "logic" / "api.ts"))
    return {normalize_path(p) for p in found if p.startswith("/")}


def mobile_screens() -> set[str]:
    return set(_MOBILE_SCREEN_RE.findall(_read(MOBILE / "navigation" / "RootNavigator.tsx")))


# ── Coletor: banco (dados invisíveis) ─────────────────────────────────────


def model_tables() -> dict[str, str]:
    """Tabela -> classe mapeada (todos os modelos registrados no metadata)."""
    from app.infrastructure.database.init_db import Base

    return {
        mapper.class_.__tablename__: mapper.class_.__name__
        for mapper in Base.registry.mappers
        if mapper.class_.__tablename__
    }


def _app_source_without_models() -> str:
    chunks: list[str] = []
    for path in _files(BACKEND / "app", (".py",)):
        if "repositories" in path.parts or path.name in {"init_db.py"}:
            continue
        chunks.append(_read(path))
    return "\n".join(chunks)


# ── Coletor: componentes órfãos ───────────────────────────────────────────

_INDEX_EXPORT_RE = re.compile(r"""export\s*\{([^}]*)\}\s*from\s*['"][^'"]+['"]""")


def feature_exports() -> dict[str, str]:
    """Nome exportado -> index.ts que o exporta, em features/*/index.ts."""
    exports: dict[str, str] = {}
    for index in sorted((FRONTEND / "features").glob("*/index.ts")):
        for block in _INDEX_EXPORT_RE.findall(_read(index)):
            for raw in block.split(","):
                name = raw.strip().removeprefix("type ").split(" as ")[-1].strip()
                if name:
                    exports[name] = str(index.relative_to(FRONTEND))
    return exports


def _frontend_references(name: str) -> int:
    pattern = re.compile(rf"\b{re.escape(name)}\b")
    hits = 0
    for path in _files(FRONTEND, (".ts", ".tsx")):
        if _is_test(path) or path.name == "index.ts":
            continue
        hits += len(pattern.findall(_read(path)))
    return hits


# ── Checagens ─────────────────────────────────────────────────────────────


def collect_findings() -> list[Finding]:
    findings: list[Finding] = []
    routes = frontend_routes()
    hrefs = nav_hrefs()
    targets = link_targets()
    linked = {path for paths in targets.values() for path in paths}
    backend = backend_routes()

    # 1. Rota ↔ navegação e links
    for href in sorted(hrefs):
        if href not in routes:
            findings.append(Finding("rota-nao-existe", href, "href da navegação aponta para rota inexistente"))
    for route in sorted(routes):
        if route in hrefs or route == "/":
            continue
        if any(
            route.startswith(target) or target.startswith(route.split("*")[0]) for target in linked if target != route
        ):
            continue
        findings.append(Finding("tela-sem-link", route, "rota sem entrada na navegação e sem link no app"))

    # 2. Chamada de API do front ↔ rota do backend
    for file, method, path in frontend_api_calls():
        if path not in backend:
            findings.append(
                Finding("tela-sem-endpoint", f"{method} {path}", f"chamada sem endpoint no backend ({file})")
            )

    # 3. IPC do desktop: renderer → preload → main
    preload = desktop_preload()
    handlers = desktop_handlers()
    emitted = desktop_emitted()
    renderer_text = renderer_source_text()
    for method, (channel, kind) in sorted(preload.items()):
        if not renderer_uses(method, renderer_text):
            findings.append(
                Finding("ipc-sem-consumidor", method, f"ponte exposta ({channel}) sem uso no renderer vivo")
            )
        elif kind == "invoke" and channel not in handlers:
            findings.append(Finding("ipc-sem-handler", channel, f"canal usado ({method}) sem handler no main"))
        elif kind == "event" and channel not in emitted:
            findings.append(Finding("ipc-evento-sem-emissor", channel, f"evento ouvido ({method}) sem emissor no main"))
    bridged = {channel for channel, _ in preload.values()}
    for channel in sorted(handlers):
        if channel not in bridged:
            findings.append(Finding("ipc-orfao", channel, "handler no main sem ponte no preload"))

    # 4. Rotas do WhatsApp ↔ consumidores
    consumers = _consumer_text()
    for route in sorted(whatsapp_routes()):
        if not _route_regex(route).search(consumers):
            findings.append(
                Finding("whatsapp-sem-consumidor", route, "rota do serviço WhatsApp sem consumidor no repo")
            )

    # 5. Mobile ↔ backend
    for path in sorted(mobile_api_paths()):
        if path not in backend and normalize_path(strip_prefix(path)) not in backend:
            findings.append(Finding("mobile-sem-endpoint", path, "chamada do app mobile sem endpoint no backend"))

    # 6. Tabelas ↔ superfície (dado invisível)
    app_source = _app_source_without_models()
    exposed = _source_text(FRONTEND, MOBILE)
    for table, cls in sorted(model_tables().items()):
        if cls in app_source or table in app_source or table in exposed:
            continue
        findings.append(Finding("dado-invisivel", table, f"tabela sem uso fora da própria camada ({cls})"))

    # 7. Componentes órfãos (feature fantasma)
    for name, index in sorted(feature_exports().items()):
        if _frontend_references(name) == 0:
            findings.append(
                Finding("componente-orfao", name, f"exportado em {index} e não renderizado em lugar nenhum")
            )

    return findings


# ── Allowlist ─────────────────────────────────────────────────────────────


def load_allowlist() -> set[tuple[str, str]]:
    if not ALLOWLIST.is_file():
        return set()
    data = json.loads(_read(ALLOWLIST) or "{}")
    return {(e["check"], e["target"]) for e in data.get("entries", [])}


def unallowed(findings: list[Finding]) -> list[Finding]:
    allowed = load_allowlist()
    return [f for f in findings if (f.check, f.target) not in allowed]


# ── Relatório ─────────────────────────────────────────────────────────────


def build_report() -> str:
    findings = collect_findings()
    pending = unallowed(findings)
    lines = [
        "# Relatório de Integridade — GasFlow",
        "",
        f"Findings: **{len(findings)}** · previstos na allowlist: **{len(findings) - len(pending)}** · pendentes: **{len(pending)}**",
        "",
        "| Check | Alvo | Detalhe |",
        "|---|---|---|",
    ]
    for f in sorted(findings, key=lambda x: (x.check, x.target)):
        mark = "" if f in pending else " _(allowlist)_"
        lines.append(f"| `{f.check}` | `{f.target}` | {f.detail}{mark} |")
    if not findings:
        lines.append("| — | — | Sem findings |")
    return "\n".join(lines) + "\n"


def write_report() -> Path:
    findings = collect_findings()
    pending = unallowed(findings)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "integrity-report.json").write_text(
        json.dumps(
            {
                "total": len(findings),
                "pending": len(pending),
                "findings": [{"check": f.check, "target": f.target, "detail": f.detail} for f in findings],
            },
            ensure_ascii=False,
            indent=2,
        )
        # newline final: o hook `check json` do pre-commit normaliza, e o
        # relatório não deve reescrever o arquivo a cada commit.
        + "\n",
        encoding="utf-8",
    )
    report = REPORT_DIR / "RELATORIO_v1.1.7.md"
    report.write_text(build_report(), encoding="utf-8")
    return report


def main() -> int:
    findings = collect_findings()
    pending = unallowed(findings)
    by_check: dict[str, int] = {}
    for f in findings:
        by_check[f.check] = by_check.get(f.check, 0) + 1
    print(f"findings={len(findings)} pendentes={len(pending)}")
    for check, total in sorted(by_check.items()):
        print(f"  {check}: {total}")
    if "--report" in sys.argv:
        print(f"relatório: {write_report()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
