"""
Community Invite Service — F5

Envia convite automático para o WhatsApp Community após cadastro de cliente.
Idempotente: 1 convite por cliente (dedup key `community:{client_codigo}`).
"""

import time
from typing import Any, Dict, Optional

from app.core.logging import setup_logging
from app.infrastructure.database.connection import SessionLocal

logger = setup_logging("INFO")

# Dedup em memória (MVP) —迁移 para Redis em produção
_invite_sent: dict = {}  # client_codigo -> timestamp
_INVITE_TTL = 86400 * 30  # 30 dias


def _get_setting(key: str, default: str = "") -> str:
    """Lê setting do banco. Fallback para default se erro."""
    try:
        from app.application.settings.settings_service import SettingsService
        from app.infrastructure.database.init_db import engine

        session = SessionLocal(bind=engine)
        try:
            return str(SettingsService(session).get_value(key, default))
        finally:
            session.close()
    except Exception:
        return default


def should_send_community_invite() -> bool:
    """Verifica se o envio de convite está habilitado (link configurado)."""
    link = _get_setting("whatsapp.community_invite_link", "")
    return bool(link and link.startswith("https://chat.whatsapp.com/"))


def is_already_invited(client_codigo: str) -> bool:
    """Verifica se o cliente já recebeu convite (idempotência)."""
    now = time.time()
    sent_at = _invite_sent.get(client_codigo)
    if sent_at and (now - sent_at) < _INVITE_TTL:
        return True
    return False


def mark_invited(client_codigo: str) -> None:
    """Marca cliente como já convidado."""
    _invite_sent[client_codigo] = time.time()


def queue_community_invite(
    client_codigo: str,
    client_nome: str,
    client_phone: str,
) -> Optional[dict]:
    """Enfileira convite para o WhatsApp Community.

    Retorna dict com status ou None se skipado.
    """
    if not should_send_community_invite():
        logger.debug("community_invite.skip", extra={"reason": "link_not_configured", "client": client_codigo})
        return None

    if is_already_invited(client_codigo):
        logger.debug("community_invite.skip", extra={"reason": "already_invited", "client": client_codigo})
        return None

    link = _get_setting("whatsapp.community_invite_link")

    # Monta mensagem
    message = (
        f"Olá {client_nome}! Bem-vindo ao GasFlow! 🔥\n\n"
        f"Entre na nossa comunidade de clientes para receber novidades, "
        f"promoções exclusivas e dicas:\n\n{link}"
    )

    # Tenta enviar via bridge (se disponível)
    try:
        from app.application.whatsapp_automation.whatsapp_bridge import WhatsAppSendBridge

        bridge = WhatsAppSendBridge()
        # Normaliza telefone
        phone_digits = "".join(c for c in client_phone if c.isdigit())
        if len(phone_digits) < 8:
            logger.warning("community_invite.skip", extra={"reason": "invalid_phone", "client": client_codigo})
            return None

        # Envia via bridge async (send_message). Chamadores são use cases
        # síncronos rodando em threadpool (endpoints `def` do FastAPI —
        # sem event loop na thread), então o caminho comum é asyncio.run;
        # dentro de um loop rodando, agenda como task fire-and-forget com
        # callback de erro (nunca derruba o cadastro).
        # F9.1 (bugfix): antes chamava `send_text`, método que nunca existiu
        # no bridge — a exceção era engolida pelo `except Exception` e o
        # convite nunca partia.
        import asyncio

        async def _send() -> Dict[str, Any]:
            return await bridge.send_message(phone_digits, message)

        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None

        if running is not None:

            def _log_task_error(task: "asyncio.Task[Any]") -> None:
                exc = task.exception()
                if exc is not None:
                    logger.error(
                        "community_invite.failed",
                        extra={"client": client_codigo, "error": str(exc)},
                    )

            running.create_task(_send()).add_done_callback(_log_task_error)
        else:
            asyncio.run(_send())

        mark_invited(client_codigo)
        logger.info("community_invite.sent", extra={"client": client_codigo, "phone": phone_digits})
        return {"status": "sent", "client_codigo": client_codigo}

    except ImportError:
        # Bridge não disponível (dev/test) — log e skip
        logger.debug("community_invite.skip", extra={"reason": "bridge_unavailable", "client": client_codigo})
        mark_invited(client_codigo)  # Marca mesmo assim para não reenviar
        return {"status": "skipped_no_bridge", "client_codigo": client_codigo}

    except Exception as e:
        logger.error("community_invite.failed", extra={"client": client_codigo, "error": str(e)})
        return {"status": "failed", "client_codigo": client_codigo, "error": str(e)}
