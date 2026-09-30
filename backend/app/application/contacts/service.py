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

# Contatos por transação na importação em lote (§18 etapa 4). 500 mantém o IN
# de telefones abaixo do limite de variáveis do SQLite: 10.000 contatos = 20
# transações em vez de 10.000 commits.
_UPSERT_CHUNK = 500


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
        """Cria ou atualiza UM contato. Retorna (client, action)."""
        telefone = normalize_phone(data.get("telefone"))
        if len(telefone) < 8:
            raise ValueError("Telefone é obrigatório (mín. 8 dígitos)")

        clean = {k: v for k, v in data.items() if k not in _PROTECTED}

        existing = self.client_repo.buscar_por_telefone(telefone)
        if existing:
            action = self._merge_into_existing(existing, clean)
            self.client_repo.atualizar(existing)
            return existing, action

        client = self._create_minimal(telefone, clean)
        self._queue_community_invites([(client.codigo, client.nome, client.telefone)])
        return client, "created"

    def _merge_into_existing(self, client: Client, data: Dict[str, Any]) -> str:
        """Aplica o payload a um cliente que JÁ existe. Devolve a action.

        Centraliza o que o upsert individual e a importação em lote precisam
        fazer igual: mesclar (só enriquece, nunca sobrescreve dado do CRM),
        carimbar last_sync_at e absorver last_interaction_at quando ainda vazio.
        """
        action = "updated" if self._apply_update(client, data) else "unchanged"
        client.last_sync_at = datetime.utcnow()
        if data.get("last_interaction_at") and not client.last_interaction_at:
            client.last_interaction_at = data["last_interaction_at"]
        return action

    @staticmethod
    def _queue_community_invites(criados: List[Tuple[str, str, str]]) -> None:
        """F5: enfileira o convite da comunidade para cada contato criado.

        Recebe tuplas (codigo, nome, telefone) em vez das entidades porque no
        lote isto roda DEPOIS do commit — ali os objetos do ORM já expiraram e
        ler cada atributo custaria 1 SELECT por contato.
        """
        for codigo, nome, telefone in criados:
            try:
                from app.application.community.service import queue_community_invite

                queue_community_invite(codigo, nome, telefone)
            except Exception:
                pass  # falha no convite não deve impedir o cadastro

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
        # Geocoding do renomeador (ADR-0001): preenche só o que está vazio.
        if data.get("cep") and not client.cep:
            client.cep = data["cep"]
            changed = True
        if data.get("entre_ruas") and not client.entre_ruas:
            client.entre_ruas = data["entre_ruas"]
            changed = True
        if data.get("cidade") and not client.cidade:
            client.cidade = data["cidade"]
            changed = True
        if data.get("uf") and not client.uf:
            client.uf = data["uf"]
            changed = True
        # Nome bruto da importação — guardado só uma vez (rastreabilidade).
        if data.get("nome_importado") and not client.nome_importado:
            client.nome_importado = data["nome_importado"]
            changed = True
        if data.get("telefone_secundario") and not client.telefone_secundario:
            secundario = normalize_phone(data["telefone_secundario"])
            if secundario and secundario != client.telefone:
                client.telefone_secundario = secundario
                changed = True
        return changed

    def _create_minimal(self, telefone: str, data: Dict[str, Any]) -> Client:
        """Cria cliente com placeholders (domínio exige nome/rua/numero/bairro)."""
        return self.client_repo.criar(self._build_new_client(telefone, data, self.client_repo.proximo_codigo()))

    def _build_new_client(self, telefone: str, data: Dict[str, Any], codigo: str) -> Client:
        """Monta — SEM gravar — o cliente novo, com os placeholders do domínio.

        `codigo` é parâmetro: na importação em lote vem do contador do bloco e
        não de proximo_codigo() por linha (que era 1 SELECT por contato criado).
        """
        nome = (data.get("nome") or "").strip() or f"Contato {telefone}"
        digits = telefone[-4:]
        # 2º telefone do card (.vcf §8.4) — nunca igual ao principal.
        secundario = normalize_phone(data.get("telefone_secundario")) if data.get("telefone_secundario") else None
        if secundario == telefone:
            secundario = None
        return Client(
            codigo=codigo,
            nome=nome,
            telefone=telefone,
            telefone_secundario=secundario,
            rua=(data.get("rua") or "A definir"),
            numero=(data.get("numero") or "S/N"),
            bairro=(data.get("bairro") or "A definir"),
            has_name=bool((data.get("nome") or "").strip()),
            is_whatsapp=bool(data.get("is_whatsapp", True)),
            marketing_status=data.get("marketing_status"),
            last_interaction_at=data.get("last_interaction_at"),
            last_sync_at=datetime.utcnow(),
            cidade=data.get("cidade"),
            uf=data.get("uf"),
            nome_importado=data.get("nome_importado"),
            cep=data.get("cep"),
            entre_ruas=data.get("entre_ruas"),
            observacoes=f"[wa-sync {digits}]" if not data.get("nome") else None,
        )

    # ── Sync em lote ──────────────────────────────────────

    def sync_batch(self, contacts: List[Dict[str, Any]], chunk_size: int = _UPSERT_CHUNK) -> List[Dict[str, Any]]:
        """Processa lote de contatos em transações de até `chunk_size` (§18/4).

        Antes: 1 SELECT + 1 commit + 1 refresh por contato — inviável para os
        10.000 contatos por arquivo do renomeador. Agora cada bloco faz 1
        SELECT dos telefones (IN), 1 leitura de código e 1 commit. O resultado
        por contato (created/updated/unchanged/error) continua idêntico e na
        mesma ordem da entrada.
        """
        if chunk_size < 1:
            chunk_size = _UPSERT_CHUNK
        results: List[Dict[str, Any]] = []
        for start in range(0, len(contacts), chunk_size):
            results.extend(self._sync_chunk(contacts[start : start + chunk_size]))
        return results

    def _sync_chunk(self, block: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Upsert de UM bloco em UMA transação (fallback linha a linha no erro)."""
        results: List[Dict[str, Any]] = [{} for _ in block]
        pendentes: List[Tuple[int, str, Dict[str, Any]]] = []
        for idx, contact in enumerate(block):
            telefone = normalize_phone(contact.get("telefone"))
            if len(telefone) < 8:
                # Mesmo contrato do upsert individual: item ruim não aborta o lote.
                results[idx] = {
                    "telefone": telefone,
                    "action": "error",
                    "error": "Telefone é obrigatório (mín. 8 dígitos)",
                }
                continue
            pendentes.append((idx, telefone, {k: v for k, v in contact.items() if k not in _PROTECTED}))

        if not pendentes:
            return results

        try:
            existentes = self.client_repo.buscar_por_telefones([t for _, t, _ in pendentes])
            criar: List[Client] = []
            atualizar: List[Client] = []
            ja_listados: set = set()
            novos: Dict[str, Client] = {}
            criados: List[Tuple[str, str, str]] = []
            proximo = int(self.client_repo.proximo_codigo())

            for idx, telefone, data in pendentes:
                existente = existentes.get(telefone) or novos.get(telefone)
                if existente is not None:
                    results[idx] = {
                        "telefone": existente.telefone,
                        "codigo": existente.codigo,
                        "action": self._merge_into_existing(existente, data),
                    }
                    # Telefone repetido no bloco: o 2º card enriquece o MESMO
                    # objeto em memória e entra uma única vez na lista de update.
                    if telefone not in ja_listados and telefone not in novos:
                        ja_listados.add(telefone)
                        atualizar.append(existente)
                    continue

                codigo = f"{proximo:06d}"
                proximo += 1
                cliente = self._build_new_client(telefone, data, codigo)
                criar.append(cliente)
                novos[telefone] = cliente
                criados.append((codigo, cliente.nome, cliente.telefone))
                results[idx] = {"telefone": cliente.telefone, "codigo": codigo, "action": "created"}

            self.client_repo.salvar_lote(criar, atualizar)
        except Exception as exc:
            # Uma linha ruim não pode derrubar o bloco inteiro: refaz linha a
            # linha, onde cada contato tem o seu próprio try/except.
            logger.warning(f"[contacts] lote falhou, refazendo linha a linha: {exc}")
            return self._sync_chunk_linha_a_linha(block)

        self._queue_community_invites(criados)
        return results

    def _sync_chunk_linha_a_linha(self, block: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Caminho antigo (1 contato por vez) — usado só quando o bloco falha."""
        results: List[Dict[str, Any]] = []
        for contact in block:
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
