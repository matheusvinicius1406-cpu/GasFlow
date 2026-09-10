"""
WhatsApp Provider Factory — WAVE 2

Creates provider adapters based on configuration.
Supports feature flags for gradual migration.

Environment variables:
- WHATSAPP_PROVIDER: current | evolution | baileys | cloud_api
- WHATSAPP_EVOLUTION_URL: Evolution API URL
- WHATSAPP_EVOLUTION_API_KEY: Evolution API key
- WHATSAPP_BAILEYS_URL: Baileys service URL
- WHATSAPP_CLOUD_API_TOKEN: Meta Cloud API access token
- WHATSAPP_CLOUD_API_PHONE_NUMBER_ID: Meta phone number ID
"""

import os
import logging
from typing import Optional

from app.domain.whatsapp_provider.contract import WhatsAppProvider

logger = logging.getLogger("gasflow.whatsapp.factory")


def create_provider(
    account_id: str,
    provider_type: Optional[str] = None,
) -> WhatsAppProvider:
    """Create a WhatsApp provider adapter based on configuration.

    Args:
        account_id: The account ID (e.g., 'primary', 'secondary')
        provider_type: Override provider type. If None, uses WHATSAPP_PROVIDER env var.

    Returns:
        WhatsAppProvider adapter instance
    """
    if provider_type is None:
        provider_type = os.getenv("WHATSAPP_PROVIDER", "current")

    provider_type = provider_type.lower()

    if provider_type == "evolution":
        return _create_evolution(account_id)
    elif provider_type == "baileys":
        return _create_baileys(account_id)
    elif provider_type in ("cloud_api", "meta"):
        return _create_cloud_api(account_id)
    elif provider_type == "current":
        return _create_current(account_id)
    else:
        logger.warning(f"[factory] Unknown provider type '{provider_type}', falling back to 'current'")
        return _create_current(account_id)


def _create_current(account_id: str) -> WhatsAppProvider:
    """Create the embedded Baileys service adapter."""
    from app.infrastructure.whatsapp_provider.current_adapter import WhatsAppWebAdapter

    service_url = os.getenv("WHATSAPP_SERVICE_URL", "http://localhost:3000")
    return WhatsAppWebAdapter(account_id=account_id, service_url=service_url)


def _create_evolution(account_id: str) -> WhatsAppProvider:
    """Create the Evolution API adapter."""
    from app.infrastructure.whatsapp_provider.evolution_adapter import EvolutionAdapter

    service_url = os.getenv("WHATSAPP_EVOLUTION_URL", "http://localhost:8080")
    api_key = os.getenv("WHATSAPP_EVOLUTION_API_KEY", "")
    instance_name = os.getenv("WHATSAPP_EVOLUTION_INSTANCE", f"gasflow-{account_id}")
    return EvolutionAdapter(
        account_id=account_id,
        service_url=service_url,
        api_key=api_key,
        instance_name=instance_name,
    )


def _create_baileys(account_id: str) -> WhatsAppProvider:
    """Create the Baileys adapter (experimental)."""
    from app.infrastructure.whatsapp_provider.baileys_adapter import BaileysAdapter

    service_url = os.getenv("WHATSAPP_BAILEYS_URL", "http://localhost:3001")
    return BaileysAdapter(account_id=account_id, service_url=service_url)


def _create_cloud_api(account_id: str) -> WhatsAppProvider:
    """Create the official Meta Cloud API adapter.

    Requer WHATSAPP_CLOUD_API_TOKEN e WHATSAPP_CLOUD_API_PHONE_NUMBER_ID.
    """
    from app.infrastructure.whatsapp_provider.cloud_api_adapter import CloudApiAdapter

    version = os.getenv("WHATSAPP_CLOUD_API_VERSION", "v21.0")
    return CloudApiAdapter(account_id=account_id, api_version=version)


def get_active_provider_type() -> str:
    """Get the currently configured provider type."""
    return os.getenv("WHATSAPP_PROVIDER", "current")
