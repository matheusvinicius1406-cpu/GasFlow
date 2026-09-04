"""
WhatsApp Session Manager — WAVE 2

Manages provider lifecycle: create, connect, disconnect, status, persist, restore.
Provider does NOT control domain directly — SessionManager orchestrates.

Architecture:
SessionManager → WhatsAppProvider → WhatsApp Service (Node.js)
"""

from typing import Dict, Optional, List
import logging

from app.domain.whatsapp_provider.contract import WhatsAppProvider
from app.domain.whatsapp_provider.models import (
    ConnectionState, ConnectionInfo, WhatsAppEvent,
)

logger = logging.getLogger("gasflow.whatsapp.session")


class WhatsAppSessionManager:
    """Manages multiple WhatsApp provider sessions."""

    def __init__(self):
        self._providers: Dict[str, WhatsAppProvider] = {}
        self._states: Dict[str, ConnectionState] = {}
        self._event_callbacks: Dict[str, list] = {}

    def register_provider(self, account_id: str, provider: WhatsAppProvider) -> None:
        """Register a provider for an account."""
        self._providers[account_id] = provider
        self._states[account_id] = ConnectionState.DISCONNECTED
        logger.info(f"[session] Registered provider for account {account_id} (type={provider.provider_type.value})")

    def get_provider(self, account_id: str) -> Optional[WhatsAppProvider]:
        """Get the provider for an account."""
        return self._providers.get(account_id)

    def get_all_providers(self) -> Dict[str, WhatsAppProvider]:
        """Get all registered providers."""
        return dict(self._providers)

    async def connect(self, account_id: str) -> bool:
        """Connect a provider."""
        provider = self._providers.get(account_id)
        if not provider:
            logger.error(f"[session] Provider not found for account {account_id}")
            return False

        try:
            self._states[account_id] = ConnectionState.CONNECTING
            await provider.start()
            self._states[account_id] = ConnectionState.CONNECTED
            logger.info(f"[session] Connected account {account_id}")
            return True
        except Exception as e:
            self._states[account_id] = ConnectionState.DISCONNECTED
            logger.error(f"[session] Failed to connect account {account_id}: {e}")
            return False

    async def disconnect(self, account_id: str) -> bool:
        """Disconnect a provider."""
        provider = self._providers.get(account_id)
        if not provider:
            return False

        try:
            await provider.stop()
            self._states[account_id] = ConnectionState.DISCONNECTED
            logger.info(f"[session] Disconnected account {account_id}")
            return True
        except Exception as e:
            logger.error(f"[session] Failed to disconnect account {account_id}: {e}")
            return False

    async def logout(self, account_id: str) -> bool:
        """Logout and destroy session."""
        provider = self._providers.get(account_id)
        if not provider:
            return False

        try:
            await provider.logout()
            self._states[account_id] = ConnectionState.DISCONNECTED
            logger.info(f"[session] Logged out account {account_id}")
            return True
        except Exception as e:
            logger.error(f"[session] Failed to logout account {account_id}: {e}")
            return False

    async def get_status(self, account_id: str) -> Optional[ConnectionInfo]:
        """Get connection status for an account."""
        provider = self._providers.get(account_id)
        if not provider:
            return None
        return await provider.get_connection_info()

    async def get_all_status(self) -> List[Dict]:
        """Get status of all accounts."""
        statuses = []
        for account_id, provider in self._providers.items():
            info = await provider.get_connection_info()
            statuses.append({
                "account_id": account_id,
                "provider_type": provider.provider_type.value,
                "status": info.to_dict(),
            })
        return statuses

    async def health_check(self, account_id: str) -> bool:
        """Health check for a specific account."""
        provider = self._providers.get(account_id)
        if not provider:
            return False
        return await provider.health_check()

    async def health_check_all(self) -> Dict[str, bool]:
        """Health check all accounts."""
        results = {}
        for account_id, provider in self._providers.items():
            try:
                results[account_id] = await provider.health_check()
            except Exception:
                results[account_id] = False
        return results

    def on_event(self, account_id: str, callback) -> None:
        """Register event callback for an account."""
        if account_id not in self._event_callbacks:
            self._event_callbacks[account_id] = []
        self._event_callbacks[account_id].append(callback)

    async def _emit_event(self, event: WhatsAppEvent) -> None:
        """Emit an event to registered callbacks."""
        callbacks = self._event_callbacks.get(event.account_id, [])
        for cb in callbacks:
            try:
                await cb(event)
            except Exception as e:
                logger.error(f"[session] Event callback error: {e}")

    def get_provider_count(self) -> int:
        """Get number of registered providers."""
        return len(self._providers)

    def get_account_ids(self) -> List[str]:
        """Get all registered account IDs."""
        return list(self._providers.keys())


# Singleton
_session_manager: Optional[WhatsAppSessionManager] = None


def get_session_manager() -> WhatsAppSessionManager:
    """Get the global session manager singleton."""
    global _session_manager
    if _session_manager is None:
        _session_manager = WhatsAppSessionManager()
    return _session_manager
