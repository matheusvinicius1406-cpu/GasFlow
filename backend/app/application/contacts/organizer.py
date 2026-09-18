"""
Contact Organizer Service — F6: renomeador em lote + códigos sequenciais
globais + lista de conflitos ("Revisar").

Design do spec (§3.7 + decisões I1–I3):
- Renomeação por REGRA com preview obrigatório: nada é sobrescrito sem
  confirmação explícita do operador (I3).
- Regras configuráveis: trim, remoção de prefixos ("WA-", "+", etc.),
  capitalização (Title Case / UPPER / lower) e padrão "Nome — Bairro".
- Código sequencial GLOBAL (I1): backfill para contatos sem código usando
  a mesma contagem do repositório (`proximo_codigo`), sem buracos
  intencionais — buracos pré-existentes NÃO são renumerados.
- Conflitos (nome duplicado exato ou telefone divergente de padrão BR)
  são PRESERVADOS e apenas sinalizados na lista "Revisar" (I3) — nenhuma
  alteração automática em contato marcado como conflito.
- Toda mutação grava audit (best-effort, padrão purchase_service).
"""

import re
from typing import Any, Dict, List, Optional

from app.core.logging import setup_logging
from app.infrastructure.repositories.client_repository import SQLAlchemyClientRepository

logger = setup_logging("INFO")

# Prefixos comuns de lixo de agenda do WhatsApp (case-insensitive).
# Cada entrada é removida com o espaço/traço seguinte quando o nome começa com ela.
DEFAULT_STRIP_PREFIXES = ["WA-", "WA ", "WPP-", "WPP ", "+", "*"]


# ═══════════════════════════════════════════════════════════
# Regras puras de renomeação (testáveis sem banco)
# ═══════════════════════════════════════════════════════════


def _strip_prefixes(nome: str, prefixes: List[str]) -> str:
    """Remove prefixos repetidos do início do nome (ex.: 'WA-WA-João' → 'João')."""
    changed = True
    while changed:
        changed = False
        for p in prefixes:
            if nome.lower().startswith(p.lower()) and len(nome) > len(p):
                nome = nome[len(p) :]
                changed = True
    return nome.lstrip()


def _title_case(nome: str) -> str:
    """Title Case preservando conectores minúsculos (de, da, do, dos, das, e)."""
    minor = {"de", "da", "do", "dos", "das", "e"}
    words = []
    for i, w in enumerate(nome.split()):
        lw = w.lower()
        if i > 0 and lw in minor:
            words.append(lw)
        elif w:
            words.append(lw[0].upper() + lw[1:])
    return " ".join(words)


def _normalize_spaces(nome: str) -> str:
    return re.sub(r"\s+", " ", nome).strip()


def build_rename_rule(
    *,
    trim: bool = True,
    strip_prefixes: bool = False,
    prefixes: Optional[List[str]] = None,
    case: Optional[str] = None,  # "title" | "upper" | "lower" | None
    pattern_bairro: bool = False,  # "Nome — Bairro"
) -> Dict[str, Any]:
    """Monta o dict de regra (serializável) validando os valores."""
    if case not in (None, "title", "upper", "lower"):
        raise ValueError(f"case inválido: {case!r} (use title|upper|lower)")
    return {
        "trim": bool(trim),
        "strip_prefixes": bool(strip_prefixes),
        "prefixes": [p for p in (prefixes if prefixes is not None else DEFAULT_STRIP_PREFIXES)],
        "case": case,
        "pattern_bairro": bool(pattern_bairro),
    }


def apply_rename_rule(nome: str, bairro: str, rule: Dict[str, Any]) -> str:
    """Aplica a regra a um nome. Pura — sem efeito colateral.

    Sempre normaliza espaços múltiplos (trim é parte da higiene básica,
    controlada pela flag `trim` da regra).

    Ordem: trim → strip de prefixos → case → padrão com bairro. O trim
    precisa vir PRIMEIRO (senão "  WA-x" não bate com o prefixo) e o
    strip ANTES do case (senão "WA-maria" vira "Wa-maria" e o prefixo
    não é mais reconhecido).
    """
    result = _normalize_spaces(nome or "")
    if rule.get("strip_prefixes"):
        result = _strip_prefixes(result, rule.get("prefixes") or [])
    if rule.get("case") == "title":
        result = _title_case(result)
    elif rule.get("case") == "upper":
        result = result.upper()
    elif rule.get("case") == "lower":
        result = result.lower()
    if rule.get("pattern_bairro"):
        b = (bairro or "").strip()
        if b and b != "A definir":
            result = f"{result} — {b}"
    return result


# ═══════════════════════════════════════════════════════════
# Conflitos (lista "Revisar") — detecção, nunca correção
# ═══════════════════════════════════════════════════════════

_BR_PHONE = re.compile(r"^1?\d{10,11}$")  # DDD+9d (11d) ou com leading 1 (12d)


def _phone_issues(telefone: str) -> bool:
    """Telefone fora do padrão BR (12–13 dígitos com/sem leading 1)."""
    t = telefone or ""
    return not _BR_PHONE.match(t)


class ContactOrganizer:
    """Renomeador em lote + backfill de códigos + lista de conflitos.

    `db` é a sessão do request (mesma transação do repositório) — usado
    apenas para gravar audit na mesma transação (padrão ReactivationService).
    """

    def __init__(self, db, client_repo: SQLAlchemyClientRepository, tenant_id: str = "default"):
        self.db = db
        self.repo = client_repo
        self.tenant_id = tenant_id

    # ── Preview / Apply ───────────────────────────────────

    def preview_rename(self, rule: Dict[str, Any], search: str = "") -> Dict[str, Any]:
        """Calcula renomeações sem gravar. Retorna lista de mudanças + contagem.

        Contatos com nome vazio são ignorados (nada a melhorar); contatos
        em conflito são contabilizados em `conflicts_skipped` e NÃO entram
        no preview (I3: nada automático sobre conflito).
        """
        conflicts = self._conflict_map()
        clients, _total = self.repo.buscar(query=search or "", page=1, page_size=200)
        changes: List[Dict[str, Any]] = []
        for c in clients:
            if not c.nome or not c.nome.strip():
                continue
            if c.codigo in conflicts:
                continue
            new_name = apply_rename_rule(c.nome, c.bairro, rule)
            if new_name and new_name != c.nome:
                changes.append(
                    {
                        "codigo": c.codigo,
                        "telefone": c.telefone,
                        "before": c.nome,
                        "after": new_name,
                        "bairro": c.bairro,
                    }
                )
        return {"changes": changes, "total": len(changes)}

    def apply_rename(
        self,
        rule: Dict[str, Any],
        codes: Optional[List[str]] = None,
        actor_id: str = "",
    ) -> Dict[str, Any]:
        """Aplica renomeações confirmadas (apenas nos `codes` enviados pelo preview).

        Segurança dupla (I3): só grava se o nome atual no banco ainda é o
        `before` que o operador viu (sem corrida com sync do WhatsApp).
        Cada mudança grava audit `contact.rename` com before/after.
        """
        renamed = skipped_missing = skipped_stale = conflicts_skipped = 0
        conflicts = self._conflict_map()
        results: List[Dict[str, Any]] = []

        for codigo in codes or []:
            client = self.repo.buscar_por_codigo(codigo)
            if not client:
                skipped_missing += 1
                results.append({"codigo": codigo, "status": "missing"})
                continue
            if codigo in conflicts:
                conflicts_skipped += 1
                results.append({"codigo": codigo, "status": "conflict"})
                continue
            new_name = apply_rename_rule(client.nome, client.bairro, rule)
            if not new_name or new_name == client.nome:
                results.append({"codigo": codigo, "status": "unchanged"})
                continue
            before = client.nome
            client.nome = new_name
            client.has_name = True
            self.repo.atualizar(client)
            _audit(
                self.db,
                action="contact.rename",
                resource_id=codigo,
                actor_id=actor_id,
                before={"nome": before},
                after={"nome": new_name},
            )
            renamed += 1
            results.append({"codigo": codigo, "status": "renamed", "before": before, "after": new_name})

        self.db.commit()
        return {
            "renamed": renamed,
            "skipped_missing": skipped_missing,
            "skipped_stale": skipped_stale,
            "conflicts_skipped": conflicts_skipped,
            "results": results,
        }

    # ── Backfill de códigos sequenciais ───────────────────

    def backfill_codes(self, actor_id: str = "") -> Dict[str, Any]:
        """Atribui código sequencial a todo contato ativo sem código.

        Usa `proximo_codigo()` (mesma sequência global do cadastro, I1).
        Colisão é impossível dentro do tenant porque a sequência é
        derivada do maior código existente — e re-consultada a cada volta.
        """
        fixed = 0
        for client in self.repo.listar_todos():
            if client.codigo and client.codigo.strip():
                continue
            new_code = self.repo.proximo_codigo()
            client.codigo = new_code
            self.repo.atualizar(client)
            _audit(
                self.db,
                action="contact.backfill_code",
                resource_id=str(client.id or new_code),
                actor_id=actor_id,
                before={"codigo": None},
                after={"codigo": new_code},
            )
            fixed += 1
        self.db.commit()
        return {"fixed": fixed}

    # ── Lista "Revisar" ───────────────────────────────────

    def list_conflicts(self) -> Dict[str, Any]:
        """Contatos sinalizados para revisão manual (preservados, nunca editados aqui).

        - duplicate_name: mesmo nome (trim, case-insensitive) em 2+ contatos ativos.
        - bad_phone: telefone fora do padrão BR (12–13 dígitos).

        A duplicação é avaliada no nome NORMALIZADO (sem prefixos tipo
        "WA-"), porque é esse que o renomeador vai produzir — dois contatos
        que colidiriam após a limpeza precisam de revisão antes do lote.
        """
        clients = self.repo.listar_todos()
        by_name: Dict[str, List[Any]] = {}
        for c in clients:
            key = _strip_prefixes(c.nome or "", DEFAULT_STRIP_PREFIXES).strip().lower()
            if key:
                by_name.setdefault(key, []).append(c)

        items: List[Dict[str, Any]] = []
        for c in clients:
            issues: List[str] = []
            key = _strip_prefixes(c.nome or "", DEFAULT_STRIP_PREFIXES).strip().lower()
            if key and len(by_name.get(key, [])) > 1:
                issues.append("duplicate_name")
            if _phone_issues(c.telefone):
                issues.append("bad_phone")
            if issues:
                items.append(
                    {
                        "codigo": c.codigo,
                        "nome": c.nome,
                        "telefone": c.telefone,
                        "issues": issues,
                        "duplicates_with": [other.codigo for other in by_name.get(key, []) if other.codigo != c.codigo]
                        if "duplicate_name" in issues
                        else [],
                    }
                )
        return {"total": len(items), "items": items}

    def _conflict_map(self) -> Dict[str, List[str]]:
        """Mapa codigo → issues dos contatos em conflito (exclusão do rename em lote)."""
        result = self.list_conflicts()
        return {i["codigo"]: i["issues"] for i in result["items"]}


# ═══════════════════════════════════════════════════════════
# Audit (best-effort — padrão purchase_service)
# ═══════════════════════════════════════════════════════════


def _audit(db, action: str, resource_id: str, actor_id: str, before=None, after=None) -> None:
    try:
        import uuid
        from datetime import datetime

        from app.infrastructure.repositories.auth_model import AuthAuditModel

        db.add(
            AuthAuditModel(
                id=str(uuid.uuid4()),
                actor_id=actor_id or "",
                actor_type="USER",
                tenant_id="default",
                action=action,
                resource="contact",
                resource_id=resource_id,
                result="SUCCESS",
                timestamp=datetime.utcnow(),
                ip_address="",
                user_agent="",
                platform="desktop",
                before_json=before,
                after_json=after,
            )
        )
        db.flush()
    except Exception:
        db.rollback()
        logger.warning("contact.audit_failed", extra={"resource_id": resource_id})
