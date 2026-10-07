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

from sqlalchemy import func

from app.application.contacts.formatter import formatar_nome_rota
from app.application.contacts.geocoding import GeocodingService, ResolverEntreRuas
from app.core.logging import setup_logging
from app.infrastructure.repositories.client_model import ClientModel
from app.infrastructure.repositories.client_repository import SQLAlchemyClientRepository
from app.infrastructure.repositories.geocode_cache_model import GeocodeCacheModel

logger = setup_logging("INFO")

# Prefixos comuns de lixo de agenda do WhatsApp (case-insensitive).
# Cada entrada é removida com o espaço/traço seguinte quando o nome começa com ela.
DEFAULT_STRIP_PREFIXES = ["WA-", "WA ", "WPP-", "WPP ", "+", "*"]

# Paginação da varredura interna (não é o tamanho da página devolvida ao
# preview): o repositório é lido em blocos para não carregar a base inteira.
_SCAN_PAGE = 500
DEFAULT_PREVIEW_PAGE_SIZE = 100
MAX_PREVIEW_PAGE_SIZE = 500

# Provedores do fallback de CEP (etapa 9 / ADR-0007) e do dado oficial do IBGE
# (Fase 3, D21). Qualquer outro valor em `geocode_cache.provider` é o provedor
# de OSM (nominatim/photon/mock).
PROVIDERS_CEP = ("brasilapi", "pontofato")
PROVIDERS_IBGE = ("ibge",)


def _sem_endereco(rua: Optional[str]) -> bool:
    """Mesmo critério do filtro `SEM_ENDERECO` do job (§jobs)."""
    return (rua or "").strip().lower() in ("", "a definir")


def _bucket_status(status: Optional[str]) -> str:
    """Bucket do `geocode_status` para a triagem (D3). `None`/`""` = pendente."""
    valor = (status or "").strip().upper()
    return valor if valor in ("OK", "NAO_ENCONTRADO") else "PENDENTE"


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
    pattern_endereco: bool = False,  # padrão de rota (etapa 7 / D5)
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
        "pattern_endereco": bool(pattern_endereco),
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


def build_new_name(client: Any, rule: Dict[str, Any], entre_ruas: Optional[str] = None) -> str:
    """Nome resultante da regra para UM contato (pura, sem banco).

    `entre_ruas` é o par **derivado** do cache por número (D12) — quem varre a
    base passa o valor do resolvedor. Quando ele vem, vence a coluna do contato
    (que guarda o que o `.vcf` trouxe); sem ele, o formatador cai na coluna.

    Dois modos:
    - `pattern_endereco` (etapa 7): formatador de nome de rota — depende do
      contato inteiro (rua/numero/cep/entre_ruas), não só do nome/bairro;
    - demais regras: `apply_rename_rule` (trim/case/padrão com bairro).

    O modo endereço tem precedência quando os dois padrões vêm ligados — o
    nome de rota já carrega o bairro no endereço, então o sufixo “— Bairro”
    seria redundante.
    """
    if rule.get("pattern_endereco"):
        return formatar_nome_rota(client, entre_ruas=entre_ruas)
    return apply_rename_rule(client.nome, client.bairro, rule)


def _entre_ruas(resolver: Optional[ResolverEntreRuas], client: Any) -> Optional[str]:
    """Par derivado do contato; `None` quando a regra não é de endereço (D12)."""
    return resolver.do_contato(client) if resolver is not None else None


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

    def __init__(
        self,
        db,
        client_repo: SQLAlchemyClientRepository,
        tenant_id: str = "default",
        geocoding: Optional[GeocodingService] = None,
    ):
        self.db = db
        self.repo = client_repo
        self.tenant_id = tenant_id
        self._geocoding = geocoding
        self._entre_ruas: Optional[ResolverEntreRuas] = None

    # ── Entre ruas derivado (D12) ───────────────

    def _geocoder(self) -> GeocodingService:
        """Geocoding injetado (testes) ou resolvido do banco na 1ª consulta."""
        if self._geocoding is None:
            self._geocoding = GeocodingService(self.db)
        return self._geocoding

    def _resolver_entre_ruas(self, rule: Dict[str, Any]) -> Optional[ResolverEntreRuas]:
        """Resolvedor do "entre A e B" (D12) — só no padrão de endereço.

        Memoizado na instância: `_select_codes` e o laço do apply do mesmo
        request compartilham as leituras, e uma regra que não é de endereço não
        paga consulta nenhuma.
        """
        if not rule.get("pattern_endereco"):
            return None
        if self._entre_ruas is None:
            self._entre_ruas = self._geocoder().resolvedor_entre_ruas()
        return self._entre_ruas

    # ── Preview / Apply ───────────────────────────────────

    # ── Seleção por filtro (preview/apply desacoplados) ──

    def _match_filter(self, client: Any, filtro: Optional[Dict[str, Any]]) -> bool:
        """Critérios derivados (bairro/status) aplicados sobre o candidato.

        `search` continua sendo resolvido pelo repositório; aqui ficam só os
        filtros que o `buscar()` não conhece.
        """
        if not filtro:
            return True
        bairro = (filtro.get("bairro") or "").strip()
        if bairro and (client.bairro or "").strip().lower() != bairro.lower():
            return False
        status = (filtro.get("status") or "").strip().upper()
        if status:
            if status == "SEM_ENDERECO":
                # Mesmo critério da triagem e do job (`_sem_endereco`): comparar
                # por igualdade crua deixaria "a definir" fora do filtro que a
                # própria tela diz que ele pertence.
                ok = _sem_endereco(client.rua)
            else:
                ok = (client.geocode_status or "").upper() == status
            if not ok:
                return False
        return True

    def _iter_candidates(self, search: str = "", filtro: Optional[Dict[str, Any]] = None):
        """Itera TODOS os candidatos que casam, paginando o repositório.

        O preview antigo lia `page_size=200` fixo e truncava a seleção em
        silêncio (renomeação parcial). Aqui não há teto: a leitura é lazy,
        bloco a bloco, para não carregar a base inteira de uma vez.
        """
        page = 1
        while True:
            clients, total = self.repo.buscar(query=search or "", page=page, page_size=_SCAN_PAGE)
            if not clients:
                return
            for client in clients:
                if self._match_filter(client, filtro):
                    yield client
            if page * _SCAN_PAGE >= total:
                return
            page += 1

    def _select_codes(
        self, rule: Dict[str, Any], search: str = "", filtro: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """Códigos que a regra REALMENTE mudaria (a mesma seleção do preview)."""
        conflicts = self._conflict_map()
        resolver = self._resolver_entre_ruas(rule)
        codes: List[str] = []
        for client in self._iter_candidates(search, filtro):
            if not client.nome or not client.nome.strip() or client.codigo in conflicts:
                continue
            new_name = build_new_name(client, rule, entre_ruas=_entre_ruas(resolver, client))
            if new_name and new_name != client.nome:
                codes.append(client.codigo)
        return codes

    def preview_rename(
        self,
        rule: Dict[str, Any],
        search: str = "",
        filtro: Optional[Dict[str, Any]] = None,
        page: int = 1,
        page_size: int = DEFAULT_PREVIEW_PAGE_SIZE,
    ) -> Dict[str, Any]:
        """Preview paginado — calcula mudanças SEM gravar (I3).

        Varre toda a base que casa com `search`/`filtro` (sem teto) e devolve
        só a página pedida, mais o `total` real. Contatos em conflito
        ("Revisar") ficam fora do preview: nada automático sobre conflito.
        """
        page = max(1, int(page or 1))
        page_size = min(max(1, int(page_size or DEFAULT_PREVIEW_PAGE_SIZE)), MAX_PREVIEW_PAGE_SIZE)
        conflicts = self._conflict_map()
        resolver = self._resolver_entre_ruas(rule)
        changes: List[Dict[str, Any]] = []
        for c in self._iter_candidates(search, filtro):
            if not c.nome or not c.nome.strip():
                continue
            if c.codigo in conflicts:
                continue
            new_name = build_new_name(c, rule, entre_ruas=_entre_ruas(resolver, c))
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
        total = len(changes)
        offset = (page - 1) * page_size
        return {
            "changes": changes[offset : offset + page_size],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, -(-total // page_size)),
        }

    def apply_rename(
        self,
        rule: Dict[str, Any],
        codes: Optional[List[str]] = None,
        actor_id: str = "",
        filtro: Optional[Dict[str, Any]] = None,
        all_matching: bool = False,
        expected: Optional[Dict[str, str]] = None,
        search: str = "",
    ) -> Dict[str, Any]:
        """Aplica renomeações confirmadas.

        Seleção (uma delas é obrigatória — nada de "aplicar a todos" implícito):
        - `codes`: lista explícita (contrato legado, ainda usado pela UI);
        - `filtro` (+ `search`): tudo que casa com o critério;
        - `all_matching=True`: toda a base que a regra mudaria (confirmação explícita).

        Segurança dupla (I3): quando `expected` traz o nome visto no preview, o
        contato é pulado se o nome atual divergir (`skipped_stale`) — sem
        corrida com o sync do WhatsApp. Cada mudança grava audit
        `contact.rename` com before/after.
        """
        if codes is None:
            if not filtro and not all_matching:
                raise ValueError("apply exige uma seleção: codes, filtro ou all_matching=True")
            codes = self._select_codes(rule, search=search, filtro=filtro)

        renamed = skipped_missing = skipped_stale = conflicts_skipped = 0
        conflicts = self._conflict_map()
        # Mesmo resolvedor de `_select_codes` (memo é da instância): seleção e
        # gravação do mesmo request enxergam exatamente o mesmo par (D12).
        resolver = self._resolver_entre_ruas(rule)
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
            seen = (expected or {}).get(codigo)
            if seen is not None and client.nome != seen:
                skipped_stale += 1
                results.append({"codigo": codigo, "status": "stale", "before": seen, "actual": client.nome})
                continue
            new_name = build_new_name(client, rule, entre_ruas=_entre_ruas(resolver, client))
            if not new_name or new_name == client.nome:
                results.append({"codigo": codigo, "status": "unchanged"})
                continue
            before = client.nome
            client.nome = new_name
            # O padrão de endereço não promove o nome a “nome de pessoa”: o
            # sufixo ({nome}) já saiu (ou foi omitido) no preview/apply. Forçar
            # has_name aqui faria o segundo apply incluir o placeholder que o
            # primeiro omitiu — quebraria a idempotência.
            if not rule.get("pattern_endereco"):
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

    # ── Origem do geocode (etapa 9) ────────────────────────

    def geocode_origem(self, limite: int = 100) -> Dict[str, Any]:
        """Resumo da ORIGEM do geocode: OSM × fallback de CEP (ADR-0007).

        A triagem precisa saber **de onde veio** cada endereço: o OSM responde
        pelo logradouro inteiro; o fallback de CEP (BrasilAPI/PontoFato) responde
        por *trecho* — e a coordenada dele não tem a mesma qualidade. Ler
        `geocode_cache.provider` é o que separa os dois, e a lista das ruas
        vindas de CEP é o que o operador confere antes de aplicar.

        A Fase 3 acrescenta a terceira origem autorizada por D21: `ibge` (o
        dado oficial do IBGE), e — por serem coisas diferentes — a origem da
        lista **entre ruas**, em `por_intersecoes_provider` (D23), que é onde
        `ibge`/`overpass` aparecem de fato neste piloto.

        `limite` corta só a LISTA (o resumo é sempre completo) — a triagem não
        pode devolver 10 mil linhas para a tela.
        """
        limite = max(1, min(int(limite or 100), 500))

        por_status: Dict[str, int] = {"OK": 0, "NAO_ENCONTRADO": 0, "PENDENTE": 0, "SEM_ENDERECO": 0}
        contatos = (
            self.db.query(ClientModel.rua, ClientModel.geocode_status)
            .filter(ClientModel.tenant_id == self.tenant_id, ClientModel.ativo.is_(True))
            .all()
        )
        for rua, status in contatos:
            if _sem_endereco(rua):
                por_status["SEM_ENDERECO"] += 1
            else:
                por_status[_bucket_status(status)] += 1

        por_origem = {"osm": 0, "cep": 0, "ibge": 0}
        por_provider: Dict[str, int] = {}
        for provider, total in (
            self.db.query(GeocodeCacheModel.provider, func.count(GeocodeCacheModel.id))
            .group_by(GeocodeCacheModel.provider)
            .all()
        ):
            nome = (provider or "desconhecido").strip().lower()
            quantidade = int(total or 0)
            por_provider[nome] = quantidade
            if nome in PROVIDERS_CEP:
                por_origem["cep"] += quantidade
            elif nome in PROVIDERS_IBGE:
                por_origem["ibge"] += quantidade
            else:
                por_origem["osm"] += quantidade

        # D23 — origem da lista ENTRE RUAS, separada da origem da coordenada.
        # `pendente` é a rua que o passe ainda não visitou; `overpass`/`ibge` é
        # quem respondeu, inclusive quando respondeu `[]` (triagem, D2).
        por_intersecoes: Dict[str, int] = {"ibge": 0, "overpass": 0, "pendente": 0}
        for provider, total in (
            self.db.query(GeocodeCacheModel.intersecoes_provider, func.count(GeocodeCacheModel.id))
            .group_by(GeocodeCacheModel.intersecoes_provider)
            .all()
        ):
            nome = (provider or "pendente").strip().lower() or "pendente"
            por_intersecoes[nome] = por_intersecoes.get(nome, 0) + int(total or 0)

        consulta_cep = self.db.query(GeocodeCacheModel).filter(GeocodeCacheModel.provider.in_(PROVIDERS_CEP))
        total_ruas_cep = int(consulta_cep.count() or 0)
        ruas_cep = [
            {
                "rua": linha.rua or "",
                "bairro": linha.bairro or "",
                "cidade": linha.cidade or "",
                "uf": linha.uf or "",
                "cep": linha.cep or "",
                "provider": (linha.provider or "").strip().lower(),
            }
            for linha in consulta_cep.order_by(GeocodeCacheModel.id).limit(limite).all()
        ]

        return {
            "por_status": por_status,
            "por_origem": por_origem,
            "por_provider": por_provider,
            "por_intersecoes_provider": por_intersecoes,
            "total_ruas_cache": sum(por_provider.values()),
            "total_ruas_cep": total_ruas_cep,
            "ruas_cep": ruas_cep,
        }


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
