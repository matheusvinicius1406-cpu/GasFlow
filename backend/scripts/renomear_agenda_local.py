"""Renomeia a agenda de contatos LOCAL desta máquina (data/app.db).

Ferramenta de operação, **não** um job do produto: ela é rodada à mão, numa
máquina só, sobre o SQLite da agenda do WhatsApp (``data/app.db`` do projeto).
O resto da frota recebe apenas a *feature* (``app.application.contacts.renamer``)
— os contatos de outras máquinas não são tocados por este script.

Por que um script e não um endpoint: a renomeação da agenda é uma escrita em
massa irreversível fora do CRM. Rodar explícito, com ``--dry-run`` por default e
backup em arquivo antes de qualquer ``UPDATE``, é o que mantém a operação
auditável e o "nada é inventado" verificável.

Uso:
    # 1) conferir o que mudaria (nada grava):
    python scripts/renomear_agenda_local.py

    # 2) aplicar (grava backup + UPDATE em uma transação):
    python scripts/renomear_agenda_local.py --apply

    # 3) com a camada de IA só nos casos que o parser não resolveu (dry-run):
    python scripts/renomear_agenda_local.py --ia

    # apontar para outro SQLite (default: <raiz do projeto>/data/app.db):
    python scripts/renomear_agenda_local.py --db ../data/app.db

Sobre ``--ia``: só consulta IA os contatos SEM endereço nenhum (o determinístico
continua obrigatório e faz a maioria). O provider vem de
``RENOMEADOR_IA_PROVIDER`` (default ``ollama`` = local, nada sai do PC). Para
usar a Hugging Face é preciso ``--ia-provider hf --confirmar-hf`` — sem a
confirmação o script avisa e não envia nada.

Saída: relatório JSON em ``export/renomear-agenda-<timestamp>.json`` com a
amostra, os contadores e (no apply) a lista ``antes → depois`` por id.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.application.contacts.renamer import renomear  # noqa: E402
from app.application.contacts.renamer_ai import precisa_ia, renomear_com_ia  # noqa: E402

# <raiz do projeto>/data/app.db — o SQLite da agenda do serviço WhatsApp. A
# raiz do projeto é 4 níveis acima: <raiz>/GasFlow/backend/scripts/este.py.
_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_DB_PADRAO = os.path.join(_RAIZ, "data", "app.db")
_EXPORT_DIR = os.path.join(_RAIZ, "export")

_AMOSTRA = 30


def _agora() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _carregar_contatos(con: sqlite3.Connection) -> List[Dict[str, Any]]:
    cur = con.cursor()
    cur.execute("SELECT id, name, phone FROM contacts WHERE name IS NOT NULL AND TRIM(name) <> '' ORDER BY id")
    return [{"id": row[0], "name": row[1], "phone": row[2]} for row in cur.fetchall()]


def planejar(contatos: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calcula o plano (sem gravar): o que muda, o que é excluído, o que fica.

    ``pendentes_ia`` é o recorte dos contatos que o parser determinístico não
    conseguiu separar (sem endereço nenhum) — é o único grupo que a camada de
    IA (``--ia``) tenta resolver.
    """
    mudancas: List[Dict[str, Any]] = []
    excluidos: List[Dict[str, Any]] = []
    pendentes_ia: List[Dict[str, Any]] = []
    mantidos = 0
    for c in contatos:
        r = renomear(c["name"])
        if r.get("excluido"):
            excluidos.append({"id": c["id"], "original": r["original"], "motivo": r["motivo"]})
            continue
        novo = r["nome_final_contato"]
        if r.get("alterado") and novo and novo != c["name"]:
            mudancas.append(
                {
                    "id": c["id"],
                    "phone": c["phone"],
                    "antes": c["name"],
                    "depois": novo,
                    "nome": r["nome"],
                    "endereco": r["endereco"],
                    "numero": r["numero"],
                    "complemento": r["complemento"],
                    "entre_ruas": r["entre_ruas"],
                    "origem": "deterministico",
                }
            )
        else:
            mantidos += 1
            if precisa_ia(r):
                pendentes_ia.append({"id": c["id"], "phone": c["phone"], "name": c["name"]})
    return {
        "mudancas": mudancas,
        "excluidos": excluidos,
        "mantidos": mantidos,
        "pendentes_ia": pendentes_ia,
    }


def _aplicar(con: sqlite3.Connection, mudancas: List[Dict[str, Any]], backup_path: str) -> None:
    """Grava o backup e aplica os UPDATE numa única transação."""
    with open(backup_path, "w", encoding="utf-8") as fh:
        json.dump(mudancas, fh, ensure_ascii=False, indent=2)

    cur = con.cursor()
    cur.executemany(
        "UPDATE contacts SET name = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?",
        [(m["depois"], m["id"]) for m in mudancas],
    )
    con.commit()


def _resumo(dados: Dict[str, Any], modo: str, db: str) -> Dict[str, Any]:
    return {
        "geradoEm": datetime.now(timezone.utc).isoformat(),
        "modo": modo,
        "db": db,
        "totalContatos": len(dados["mudancas"]) + len(dados["excluidos"]) + dados["mantidos"],
        "alterados": len(dados["mudancas"]),
        "excluidos": len(dados["excluidos"]),
        "mantidos": dados["mantidos"],
        "amostra": dados["mudancas"][:_AMOSTRA],
        "excluidos_detalhe": dados["excluidos"],
    }


def _rodar_ia(args: argparse.Namespace, dados: Dict[str, Any]) -> Dict[str, Any]:
    """Camada opcional de IA: resolve só os pendentes (contatos sem endereço).

    O determinístico continua obrigatório — a IA só **acrescenta** mudanças
    validadas; o que ela não resolver (ou alucinar) fica como estava.
    """
    stats: Dict[str, Any] = {
        "pendentes": len(dados.get("pendentes_ia", [])),
        "enviados": 0,
        "aplicados": 0,
        "ignorados": 0,
        "sem_resposta": 0,
        "provider": None,
    }
    if not args.ia or not dados.get("pendentes_ia"):
        return stats

    from app.application.ai.provider_factory import get_renamer_provider  # noqa: PLC0415
    from app.core.config import settings  # noqa: PLC0415

    settings.renomeador_ia = True
    if args.ia_provider:
        settings.renomeador_ia_provider = args.ia_provider
    stats["provider"] = settings.renomeador_ia_provider

    # Trava de privacidade: a HF é nuvem — sem confirmação explícita, não sai
    # um byte da agenda do PC.
    if settings.renomeador_ia_provider == "hf" and not args.confirmar_hf:
        print(
            "AVISO: --ia-provider hf enviaria nomes/endereços para fora do PC. "
            "NADA foi enviado. Repita com --confirmar-hf para autorizar, "
            "ou use o default local (--ia-provider ollama)."
        )
        stats["provider"] = "hf (bloqueado: falta --confirmar-hf)"
        return stats

    provider = get_renamer_provider()
    if provider is None:
        stats["provider"] = f"{settings.renomeador_ia_provider} (indisponível)"
        return stats
    stats["provider"] = provider.model_name

    # Chaves repetidas: um nome compartilhado por 2 contatos vira 1 chamada.
    pendentes = dados["pendentes_ia"]
    if getattr(args, "limit_ia", 0) > 0:
        pendentes = pendentes[: int(args.limit_ia)]
    stats["enviados"] = len(pendentes)
    por_nome: Dict[str, List[Dict[str, Any]]] = {}
    for p in pendentes:
        por_nome.setdefault(p["name"], []).append(p)

    brutos = list(por_nome)
    respostas = renomear_com_ia(brutos, provider, lote=int(getattr(settings, "renomeador_ia_lote", 8)))
    stats["sem_resposta"] = len(brutos) - len(respostas)

    for bruto, val in respostas.items():
        # Trava de preservação: "excluir: true" (pix/portaria/trote...) significa
        # "não renomear, apenas sinalizar" — o contato fica exatamente como está.
        # Sem isto, o modelo (medido no qwen3:1.7b) devolve excluir=true para
        # nomes comuns de negócio e encurtaria "Augusto Montenegro Atrás Do Loro
        # Motos" -> "Augusto Montenegro", perdendo informação do contato.
        if val.get("excluir"):
            stats["ignorados"] += len(por_nome.get(bruto, []))
            continue
        novo = val.get("nome_final_contato")
        for p in por_nome.get(bruto, []):
            if not novo or novo == p["name"]:
                stats["ignorados"] += 1
                continue
            dados["mudancas"].append(
                {
                    "id": p["id"],
                    "phone": p["phone"],
                    "antes": p["name"],
                    "depois": novo,
                    "nome": val.get("nome"),
                    "endereco": val.get("endereco"),
                    "numero": val.get("numero"),
                    "complemento": val.get("complemento"),
                    "entre_ruas": val.get("entre_ruas"),
                    "origem": "ia",
                }
            )
            stats["aplicados"] += 1
            dados["mantidos"] = max(0, dados["mantidos"] - 1)
    return stats


def main() -> int:
    # Console Windows pode ser cp1252 (sem "→" nem "…"): em vez de derrubar o
    # script no fim com UnicodeEncodeError, troca o caractere por "?".
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(errors="replace")
        except Exception:  # noqa: BLE001 - stream de teste/pytest não tem reconfigure
            pass

    parser = argparse.ArgumentParser(description="Renomeia a agenda local de contatos (data/app.db)")
    parser.add_argument("--db", default=_DB_PADRAO, help=f"SQLite da agenda (default: {_DB_PADRAO})")
    parser.add_argument("--apply", action="store_true", help="aplica de verdade (default: dry-run)")
    parser.add_argument("--ia", action="store_true", help="acrescenta a camada de IA nos contatos sem endereço")
    parser.add_argument(
        "--ia-provider",
        default=None,
        choices=["ollama", "hf"],
        help="provider da IA (default: env RENOMEADOR_IA_PROVIDER, ollama local)",
    )
    parser.add_argument(
        "--confirmar-hf",
        action="store_true",
        help="autoriza enviar nomes/endereços para a Hugging Face (sem isso, nada sai do PC)",
    )
    parser.add_argument(
        "--limit-ia",
        type=int,
        default=0,
        help="limita quantos pendentes vão para a IA (0 = todos); útil para piloto",
    )
    args = parser.parse_args()

    if not os.path.isfile(args.db):
        raise SystemExit(f"banco não encontrado: {args.db}")

    inicio = time.monotonic()
    con = sqlite3.connect(args.db)
    try:
        contatos = _carregar_contatos(con)
        dados = planejar(contatos)
        ia_stats = _rodar_ia(args, dados)

        os.makedirs(_EXPORT_DIR, exist_ok=True)
        relatorio = os.path.join(_EXPORT_DIR, f"renomear-agenda-{_agora()}.json")

        resumo = _resumo(dados, "apply" if args.apply else "dry-run", args.db)
        resumo["ia"] = ia_stats
        backup_path = None
        if args.apply and dados["mudancas"]:
            backup_path = os.path.join(_EXPORT_DIR, f"renomear-agenda-backup-{_agora()}.json")
            _aplicar(con, dados["mudancas"], backup_path)
            resumo["backup"] = backup_path

        with open(relatorio, "w", encoding="utf-8") as fh:
            json.dump({**resumo, "mudancas": dados["mudancas"]}, fh, ensure_ascii=False, indent=2)
    finally:
        con.close()

    print(f"db                  : {args.db}")
    print(f"modo                : {'APPLY' if args.apply else 'DRY-RUN (nada gravado)'}")
    print(f"contatos lidos      : {len(contatos)}")
    print(f"seriam alterados    : {len(dados['mudancas'])}")
    print(f"excluídos (§4)      : {len(dados['excluidos'])}")
    print(f"mantidos            : {dados['mantidos']}")
    print(f"IA provider         : {ia_stats['provider'] or 'desligada (--ia não informado)'}")
    print(f"IA pendentes        : {ia_stats['pendentes']}")
    print(f"IA enviados         : {ia_stats['enviados']}")
    print(f"IA aplicados        : {ia_stats['aplicados']}")
    print(f"IA sem resposta     : {ia_stats['sem_resposta']}")
    if backup_path:
        print(f"backup              : {backup_path}")
    print(f"relatório           : {relatorio}")
    print(f"tempo               : {time.monotonic() - inicio:.1f}s")

    if dados["mudancas"]:
        print("\namostra (antes → depois):")
        for m in dados["mudancas"][:_AMOSTRA]:
            origem = f" [{m.get('origem', 'deterministico')}]"
            print(f"  {m['antes']}\n    → {m['depois']}{origem}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
