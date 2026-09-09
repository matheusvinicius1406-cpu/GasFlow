"""
Contact CRM Service — sync WhatsApp ↔ clientes do CRM.

Upsert idempotente por telefone normalizado, enriquecimento de endereço
via LLM e import/export VCF. Opera sobre a entidade Client EXISTENTE
(código de 6 dígitos gerado pelo repositório; nada de UUID/sequência).

Regras de upsert (chave: telefone normalizado):
- existe  → atualiza nome/endereço quando o novo dado é mais rico,
            preserva codigo/id do CRM;
- não existe → cria com placeholders obrigatórios do domínio
            (nome="Contato <tel>", rua="A definir", numero="S/N",
            bairro="A definir") para satisfazer as validações da entidade.
"""

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.core.logging import setup_logging
from app.domain.client.entity import Client
from app.infrastructure.repositories.client_repository import SQLAlchemyClientRepository

logger = setup_logging("INFO")

# Campos do payload de sync que NUNCA sobrescrevem o CRM.
_PROTECTED = {"codigo", "id", "tenant_id", "created_at", "updated_at"}


def normalize_phone(phone: Optional[str]) -> str:
    """Só dígitos (sem '+'/'('/')'/'-'/' '). None → ''."""
    if not phone:
        return ""
    return "".join(ch for ch in str(phone) if ch.isdigit())


class ContactService:
    """Upsert/enriquecimento de contatos do WhatsApp no CRM."""

    def __init__(self, client_repo: SQLAlchemyClientRepository, llm_provider=None):
        self.client_repo = client_repo
        # LLM injetado (testes) ou resolvido do factory (mock em dev/testes).
        self.llm_provider = llm_provider

    # ── Upsert ────────────────────────────────────────────

    def upsert_contact(self, data: Dict[str, Any]) -> Tuple[Client, str]:
        """Cria ou atualiza um contato. Retorna (client, action)."""
        telefone = normalize_phone(data.get("telefone"))
        if len(telefone) < 8:
            raise ValueError("Telefone é obrigatório (mín. 8 dígitos)")

        clean = {k: v for k, v in data.items() if k not in _PROTECTED}

        existing = self.client_repo.buscar_por_telefone(telefone)
        if existing:
            action = "updated" if self._apply_update(existing, clean) else "unchanged"
            existing.last_sync_at = datetime.utcnow()
            if data.get("last_interaction_at") and not existing.last_interaction_at:
                existing.last_interaction_at = data["last_interaction_at"]
            self.client_repo.atualizar(existing)
            return existing, action

        return self._create_minimal(telefone, clean), "created"

    def _apply_update(self, client: Client, data: Dict[str, Any]) -> bool:
        """Atualiza campos quando o novo valor é mais rico. True se mudou."""
        changed = False
        # Nome: só preenche se o CRM ainda tem o placeholder.
        nome = (data.get("nome") or "").strip()
        if nome and (not client.nome or client.nome.startswith("Contato ")):
            client.nome = nome
            client.has_name = True
            changed = True
        if data.get("is_whatsapp") is not None and client.is_whatsapp is None:
            client.is_whatsapp = bool(data["is_whatsapp"])
            changed = True
        if data.get("marketing_status") and not client.marketing_status:
            client.marketing_status = data["marketing_status"]
            changed = True
        return changed

    def _create_minimal(self, telefone: str, data: Dict[str, Any]) -> Client:
        """Cria cliente com placeholders (domínio exige nome/rua/numero/bairro)."""
        nome = (data.get("nome") or "").strip() or f"Contato {telefone}"
        digits = telefone[-4:]
        client = Client(
            codigo=self.client_repo.proximo_codigo(),
            nome=nome,
            telefone=telefone,
            rua=(data.get("rua") or "A definir"),
            numero=(data.get("numero") or "S/N"),
            bairro=(data.get("bairro") or "A definir"),
            has_name=bool((data.get("nome") or "").strip()),
            is_whatsapp=bool(data.get("is_whatsapp", True)),
            marketing_status=data.get("marketing_status"),
            last_interaction_at=data.get("last_interaction_at"),
            last_sync_at=datetime.utcnow(),
            observacoes=f"[wa-sync {digits}]" if not data.get("nome") else None,
        )
        return self.client_repo.criar(client)

    # ── Sync em lote ──────────────────────────────────────

    def sync_batch(self, contacts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Processa lote de contatos sincronizados do serviço WhatsApp."""
        results: List[Dict[str, Any]] = []
        for contact in contacts:
            try:
                client, action = self.upsert_contact(contact)
                results.append(
                    {
                        "telefone": client.telefone,
                        "codigo": client.codigo,
                        "action": action,
                    }
                )
            except Exception as exc:  # lote nunca aborta por 1 contato ruim
                logger.warning(f"[contacts] upsert falhou: {exc}")
                results.append(
                    {
                        "telefone": normalize_phone(contact.get("telefone")),
                        "action": "error",
                        "error": str(exc),
                    }
                )
        return results

    # ── Enriquecimento via LLM ────────────────────────────

    def enrich_with_ai(self, codigo: str) -> Dict[str, Any]:
        """Extrai nome/endereço embutido no campo de nome via LLM.

        Só roda para clientes vindos do WhatsApp (has_name False ou nome
        placeholder) e sem endereço real. Falha do LLM = no-op seguro.
        """
        client = self.client_repo.buscar_por_codigo(codigo)
        if not client:
            return {"success": False, "error": "Cliente não encontrado"}
        if client.rua not in (None, "", "A definir"):
            return {"success": False, "error": "Endereço já preenchido — nada a enriquecer"}

        if self.llm_provider is None:
            from app.infrastructure.ai.factory import get_llm_provider

            self.llm_provider = get_llm_provider()

        prompt = (
            "Você extrai dados de endereço de nomes de contatos de WhatsApp de uma "
            "revenda de gás e água. Responda APENAS um JSON válido:\n"
            '{"nome": "...", "rua": "...", "numero": "...", "complemento": "...", "bairro": "..."}\n'
            "Campos inexistentes = string vazia. Nome do contato: "
            f'"{client.nome}"'
        )
        try:
            from app.domain.ai.provider import LLMMessage, LLMRole

            response = self.llm_provider.generate([LLMMessage(role=LLMRole.USER, content=prompt)], temperature=0.1)
            if response.error or not response.content:
                return {"success": False, "error": response.error or "LLM vazio"}
            data = json.loads(self._extract_json(response.content))
            if not (data.get("rua") or data.get("bairro") or data.get("numero")):
                return {"success": True, "enriched": False, "reason": "nenhum dado de endereço no nome"}
            client.nome = data.get("nome") or client.nome
            client.rua = data.get("rua") or client.rua
            client.numero = data.get("numero") or client.numero
            client.complemento = data.get("complemento") or client.complemento
            client.bairro = data.get("bairro") or client.bairro
            self.client_repo.atualizar(client)
            return {"success": True, "enriched": True, "codigo": client.codigo}
        except json.JSONDecodeError:
            return {"success": False, "error": "LLM não retornou JSON válido"}
        except Exception as exc:
            logger.warning(f"[contacts] enriquecimento falhou para {codigo}: {exc}")
            return {"success": False, "error": str(exc)}

    @staticmethod
    def _extract_json(text: str) -> str:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        return match.group(0) if match else text
