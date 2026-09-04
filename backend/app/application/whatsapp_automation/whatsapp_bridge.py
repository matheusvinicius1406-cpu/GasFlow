"""
WhatsApp Send Bridge — FASE 14.5

Connects FastAPI automation executions to the WhatsApp Node.js service.
Handles: send, retry, audit logging, idempotency.

Architecture:
FastAPI AutomationService → WhatsAppSendBridge → HTTP POST → Node.js /send → WhatsApp Provider
"""

import httpx
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional
from app.core.config import settings
from app.core.logging import setup_logging

logger = setup_logging("INFO")

# Retry configuration
MAX_RETRIES = 3
RETRY_BASE_DELAY_MS = 1000
RETRY_MAX_DELAY_MS = 10000

# Timeout
SEND_TIMEOUT_SECONDS = 30


class WhatsAppSendBridge:
    """Bridge between FastAPI automation and WhatsApp Node.js service."""

    def __init__(self, service_url: Optional[str] = None):
        self.service_url = (service_url or settings.whatsapp_service_url).rstrip("/")

    async def send_message(
        self,
        phone: str,
        text: str,
        account_id: str = "primary",
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a WhatsApp message via the Node.js service.

        Returns:
            {"success": bool, "message_id": str|None, "error": str|None}
        """
        if not idempotency_key:
            idempotency_key = self._generate_idempotency_key(phone, text)

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=SEND_TIMEOUT_SECONDS) as client:
                    response = await client.post(
                        f"{self.service_url}/send",
                        json={
                            "accountId": account_id,
                            "recipient": phone,
                            "text": text,
                            "idempotencyKey": idempotency_key,
                        },
                    )

                    if response.status_code == 200:
                        data = response.json()
                        if data.get("success"):
                            logger.info(
                                f"[whatsapp-bridge] Message sent to {phone} "
                                f"(msg_id={data.get('messageId')})"
                            )
                            return {
                                "success": True,
                                "message_id": data.get("messageId"),
                                "error": None,
                            }
                        else:
                            last_error = data.get("error", "Unknown error")
                            logger.warning(
                                f"[whatsapp-bridge] Send failed (attempt {attempt+1}): {last_error}"
                            )
                    elif response.status_code == 429:
                        # Rate limited — back off
                        last_error = "Rate limited by WhatsApp service"
                        logger.warning(f"[whatsapp-bridge] Rate limited (attempt {attempt+1})")
                    else:
                        last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                        logger.warning(
                            f"[whatsapp-bridge] Unexpected status (attempt {attempt+1}): {response.status_code}"
                        )

            except httpx.TimeoutException:
                last_error = "Timeout connecting to WhatsApp service"
                logger.warning(f"[whatsapp-bridge] Timeout (attempt {attempt+1})")
            except httpx.ConnectError:
                last_error = "Cannot connect to WhatsApp service"
                logger.warning(f"[whatsapp-bridge] Connection error (attempt {attempt+1})")
            except Exception as e:
                last_error = str(e)
                logger.error(f"[whatsapp-bridge] Unexpected error (attempt {attempt+1}): {e}")

            # Exponential backoff with jitter
            if attempt < MAX_RETRIES - 1:
                import asyncio
                delay = min(
                    RETRY_MAX_DELAY_MS,
                    RETRY_BASE_DELAY_MS * (2 ** attempt)
                )
                await asyncio.sleep(delay / 1000)

        logger.error(f"[whatsapp-bridge] All {MAX_RETRIES} attempts failed for {phone}")
        return {
            "success": False,
            "message_id": None,
            "error": last_error or "All retry attempts exhausted",
        }

    async def check_connection(self, account_id: str = "primary") -> Dict[str, Any]:
        """Check if WhatsApp service and account are connected."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self.service_url}/status")
                if response.status_code == 200:
                    data = response.json()
                    accounts = data.get("accounts", [])
                    for acc in accounts:
                        if acc.get("id") == account_id:
                            return {
                                "connected": acc.get("status", {}).get("connected", False),
                                "phone": acc.get("phone"),
                            }
                    return {"connected": False, "phone": None}
        except Exception as e:
            logger.warning(f"[whatsapp-bridge] Connection check failed: {e}")
        return {"connected": False, "phone": None}

    def _generate_idempotency_key(self, phone: str, text: str) -> str:
        """Generate a deterministic idempotency key."""
        raw = f"{phone}:{text}:{datetime.utcnow().strftime('%Y%m%d%H')}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]
