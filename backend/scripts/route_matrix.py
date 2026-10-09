"""Gera a matriz de rotas do GasFlow a partir do app FastAPI montado.

Uso (dentro de backend/):
    python scripts/route_matrix.py ../docs/seguranca/matriz-de-rotas.json

Saida: JSON com todas as operacoes (method+path) classificadas por nivel de
acesso, + sumario. Uma copia .md e gerada ao lado quando o caminho termina
em .json.

Classificacao derivada das dependencias FastAPI efetivas (incluindo
dependencias aninhadas, ex. `Depends(_svc)` cujo `_svc` usa
`require_permission`). Nao ha middleware global de auth — ver app/main.py.
"""

import json
import os
import sys
from collections import Counter

BACKEND_DIR = os.environ.get("GASFLOW_BACKEND_DIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)

from fastapi.routing import APIRoute  # noqa: E402

from app.main import app  # noqa: E402

# Dependencias de acesso conhecidas -> classificacao
AUTH_DEPS = {
    "get_tenant_context": "AUTENTICADA",
    "require_admin": "ADMIN",
    "require_permission": "PERMISSAO",
    "require_permission_any": "PERMISSAO",
    "require_role": "ROLE",
    "require_driver": "ENTREGADOR",
    "_authenticate_driver": "ENTREGADOR",
    "get_mobile_context": "ENTREGADOR",
    "_get_service": "AUTENTICADA",
    "get_db": "SOMENTE_DB",
    "require_whatsapp_service": "SERVICO",
    "require_whatsapp_service_or_user": "SERVICO_OU_USER",
    "_require_relay_service_key": "SERVICO",
    "_require_service_key": "SERVICO",
    "require_integration_token": "TOKEN_INTEGRACAO",
    "require_renamer_enabled": "FLAG_RENOMEADOR",
}

PUBLIC_BY_DESIGN = {
    "/login",
    "/auth/login",
    "/auth/refresh",
    "/cadastro",
    "/driver/login",
    "/driver/auth/login",
    "/auth/mobile/login",
    "/auth/mobile/refresh",
}


def walk(routes, prefix="", extra_deps=()):
    """Percorre app.routes tratando APIRoute, routers aninhados (FastAPI 0.141
    guarda include_router como _IncludedRouter) e rotas simples (WS/SPA)."""
    out = []
    for r in routes:
        if isinstance(r, APIRoute):
            out.append((prefix, r, tuple(extra_deps)))
            continue
        name = type(r).__name__
        if name == "_IncludedRouter":
            ctx = getattr(r, "include_context", None)
            pfx = prefix + (getattr(ctx, "prefix", "") or "")
            deps = list(extra_deps) + list(getattr(ctx, "dependencies", ()) or ())
            inner = getattr(r, "original_router", None)
            if inner is not None:
                out.extend(walk(inner.routes, pfx, deps))
            continue
        sub = getattr(r, "routes", None)
        if sub:
            out.extend(walk(sub, prefix, extra_deps))
        elif hasattr(r, "path"):
            out.append((prefix, r, tuple(extra_deps)))
    return out


def dep_names(route, extra_deps=(), _depth=0, _seen=None):
    """Coleta nomes de dependencias; segue dependencias aninhadas (ex.:
    `svc = Depends(_svc)` onde `_svc` internamente usa require_permission)."""
    if _seen is None:
        _seen = set()
    names = set()
    import inspect

    def add(dep, depth):
        call = getattr(dep, "dependency", None) or getattr(dep, "call", None)
        if call is None:
            return
        name = getattr(call, "__name__", str(call))
        qual = getattr(call, "__qualname__", "")
        # factories (require_permission("x"), require_role(...)) devolvem um
        # closure interno (_check); o qualname carrega o nome da fabrica
        if ".<locals>." in qual:
            factory = qual.split(".<locals>.")[0]
            if factory.startswith("require_") or factory.startswith("get_"):
                name = factory
        names.add(name)
        # desce na assinatura da propria dependencia (ate 4 niveis)
        if depth >= 4 or name in _seen:
            return
        _seen.add(name)
        try:
            sig = inspect.signature(call)
        except (ValueError, TypeError):
            return
        for p in sig.parameters.values():
            add(p.default, depth + 1)

    for d in list(getattr(route, "dependencies", []) or []) + list(extra_deps or ()):
        add(d, _depth)
    endpoint = getattr(route, "endpoint", None)
    if endpoint is not None:
        try:
            sig = inspect.signature(endpoint)
        except (ValueError, TypeError):
            return names
        for p in sig.parameters.values():
            add(p.default, _depth + 1)
            anno = str(p.annotation)
            for key in AUTH_DEPS:
                if key in anno:
                    names.add(key)
    return names


AUTH_CLASSES = {
    "ADMIN",
    "PERMISSAO",
    "ROLE",
    "ENTREGADOR",
    "SERVICO",
    "SERVICO_OU_USER",
    "TOKEN_INTEGRACAO",
    "AUTENTICADA",
}
RESTRICTIVE_ORDER = [
    "ADMIN",
    "PERMISSAO",
    "ROLE",
    "ENTREGADOR",
    "SERVICO",
    "SERVICO_OU_USER",
    "TOKEN_INTEGRACAO",
    "AUTENTICADA",
]


def classify(route, names, path):
    hits = [n for n in names if n in AUTH_DEPS]
    classes = {AUTH_DEPS[h] for h in hits}
    auth_hits = [h for h in hits if AUTH_DEPS[h] in AUTH_CLASSES]
    if auth_hits:
        for o in RESTRICTIVE_ORDER:
            if any(AUTH_DEPS[h] == o for h in auth_hits):
                return o, sorted(hits)
    if "SOMENTE_DB" in classes:
        return "SOMENTE_DB", sorted(hits)
    # sem dependencia de auth: separa intencional x nao intencional
    for p in PUBLIC_BY_DESIGN:
        if path.endswith(p) or path == p or path.endswith("/" + p.lstrip("/")):
            return "PUBLICA_DESIGN", sorted(hits)
    if getattr(route, "include_in_schema", True) is False:
        return "FORA_DO_SCHEMA", sorted(hits)
    return "SEM_AUTH?", sorted(hits)


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "route_matrix.json"
    entries = []
    for prefix, route, extra_deps in walk(app.routes):
        methods = sorted(getattr(route, "methods", []) or [])
        path = prefix + getattr(route, "path", "")
        if not methods:
            continue
        names = dep_names(route, extra_deps)
        cls, hits = classify(route, names, path)
        entries.append(
            {
                "path": path,
                "methods": methods,
                "class": cls,
                "deps": hits,
                "tags": getattr(route, "tags", []),
                "name": getattr(route, "name", ""),
            }
        )
    entries.sort(key=lambda e: (e["path"], e["methods"]))
    summary = Counter(e["class"] for e in entries)
    result = {
        "total_operations": len(entries),
        "distinct_paths": len({e["path"] for e in entries}),
        "summary": dict(summary.most_common()),
        "routes": entries,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    md_path = None
    if out_path.endswith(".json"):
        md_path = out_path[:-5] + ".md"
        write_markdown(result, md_path)
    print("total_operations:", result["total_operations"])
    print("distinct_paths:", result["distinct_paths"])
    for k, v in result["summary"].items():
        print(f"  {k}: {v}")
    if md_path:
        print("markdown:", md_path)


def write_markdown(result, md_path):
    from datetime import datetime, timezone

    lines = [
        "# Matriz de rotas — GasFlow",
        "",
        f"Gerado em {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} por "
        "`python scripts/route_matrix.py <saida.json>` (dentro de `backend/`).",
        "",
        f"- **Operações (method+path):** {result['total_operations']}",
        f"- **Paths distintos:** {result['distinct_paths']}",
        "",
        "## Sumário por classe",
        "",
        "| Classe | Operações | Significado |",
        "|---|---:|---|",
    ]
    meaning = {
        "ADMIN": "Exige role ADMIN / `admin.*`",
        "PERMISSAO": "Exige permissão RBAC explícita (`require_permission`)",
        "ROLE": "Exige uma das roles do `require_role`",
        "AUTENTICADA": "Exige sessão/JWT válido (`get_tenant_context`)",
        "ENTREGADOR": "Sessão de entregador (app/mobile)",
        "SERVICO": "Chave de serviço `X-GasFlow-Key` (fail-closed)",
        "SERVICO_OU_USER": "Chave de serviço **ou** usuário autenticado",
        "TOKEN_INTEGRACAO": "`X-Integration-Token` por integração",
        "SOMENTE_DB": "Só `get_db` — sem auth no caminho (analisar)",
        "SEM_AUTH?": "Sem dependência de auth identificada (analisar)",
        "PUBLICA_DESIGN": "Pública por projeto (login/refresh/driver)",
        "FORA_DO_SCHEMA": "Rotas fora do OpenAPI (/docs, /redoc)",
        "FLAG_RENOMEADOR": "Só flag de feature (não é auth)",
    }
    for k, v in result["summary"].items():
        lines.append(f"| `{k}` | {v} | {meaning.get(k, '')} |")
    lines += ["", "## Rotas sem auth efetiva (`SEM_AUTH?` / `SOMENTE_DB`)", ""]
    lines += ["| Método | Path | Deps encontradas |", "|---|---|---|"]
    for e in result["routes"]:
        if e["class"] in ("SEM_AUTH?", "SOMENTE_DB"):
            lines.append(f"| {', '.join(e['methods'])} | `{e['path']}` | {', '.join(e['deps']) or '—'} |")
    lines += ["", "## Operações protegidas (todas as classes com auth)", ""]
    lines += ["| Classe | Método | Path |", "|---|---|---|"]
    for e in result["routes"]:
        if e["class"] not in ("SEM_AUTH?", "SOMENTE_DB", "FORA_DO_SCHEMA"):
            lines.append(f"| `{e['class']}` | {', '.join(e['methods'])} | `{e['path']}` |")
    lines.append("")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
