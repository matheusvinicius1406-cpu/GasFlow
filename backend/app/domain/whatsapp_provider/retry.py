"""
WhatsApp Provider Retry Policy — WAVE 2

Centralized retry logic. Providers report success/temporary failure/permanent failure.
Retry policy handles the rest.

Architecture:
Provider → result(success/temporary/permanent) → RetryPolicy → retry or dead letter
"""

import asyncio
import logging
from typing import Callable, Awaitable, Any, Optional
from app.domain.whatsapp_provider.errors import WhatsAppError, WhatsAppErrorType

logger = logging.getLogger("gasflow.whatsapp.retry")


class RetryPolicy:
    """Centralized retry policy for WhatsApp operations."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay_ms: int = 1000,
        max_delay_ms: int = 30000,
        jitter_ratio: float = 0.3,
    ):
        self.max_retries = max_retries
        self.base_delay_ms = base_delay_ms
        self.max_delay_ms = max_delay_ms
        self.jitter_ratio = jitter_ratio
        self._metrics = {
            "total_attempts": 0,
            "total_retries": 0,
            "total_successes": 0,
            "total_failures": 0,
            "permanent_failures": 0,
        }

    async def execute_with_retry(
        self,
        operation: Callable[..., Awaitable[Any]],
        *args,
        operation_name: str = "unknown",
        **kwargs,
    ) -> Any:
        """Execute an operation with retry on temporary failures.

        Returns the result on success.
        Raises WhatsAppError on permanent failure after all retries exhausted.
        """
        last_error = None

        for attempt in range(self.max_retries + 1):
            self._metrics["total_attempts"] += 1
            try:
                result = await operation(*args, **kwargs)
                self._metrics["total_successes"] += 1
                return result
            except WhatsAppError as e:
                last_error = e
                if not e.retryable:
                    # Permanent failure — no retry
                    self._metrics["permanent_failures"] += 1
                    logger.error(f"[retry] Permanent failure in {operation_name}: {e}")
                    raise
                # Temporary failure — retry
                if attempt < self.max_retries:
                    self._metrics["total_retries"] += 1
                    delay = self._calculate_delay(attempt)
                    logger.warning(
                        f"[retry] Temporary failure in {operation_name} "
                        f"(attempt {attempt + 1}/{self.max_retries + 1}), "
                        f"retrying in {delay}ms"
                    )
                    await asyncio.sleep(delay / 1000)
            except Exception as e:
                # Unknown error — treat as permanent
                self._metrics["permanent_failures"] += 1
                logger.error(f"[retry] Unknown error in {operation_name}: {e}")
                raise WhatsAppError(
                    str(e),
                    error_type=WhatsAppErrorType.UNKNOWN,
                    retryable=False,
                    raw_error=e,
                )

        # All retries exhausted
        self._metrics["total_failures"] += 1
        logger.error(f"[retry] All retries exhausted for {operation_name}")
        if last_error:
            raise last_error
        raise WhatsAppError(
            f"All {self.max_retries} retries exhausted for {operation_name}",
            error_type=WhatsAppErrorType.UNKNOWN,
            retryable=False,
        )

    def _calculate_delay(self, attempt: int) -> int:
        """Calculate delay with exponential backoff and jitter."""
        import random

        base = min(self.max_delay_ms, self.base_delay_ms * (2**attempt))
        jitter = base * self.jitter_ratio * (random.random() * 2 - 1)
        return max(100, int(base + jitter))

    def get_metrics(self) -> dict:
        """Get retry metrics."""
        return dict(self._metrics)

    def reset_metrics(self) -> None:
        """Reset metrics."""
        for key in self._metrics:
            self._metrics[key] = 0


# Singleton
_retry_policy: Optional[RetryPolicy] = None


def get_retry_policy() -> RetryPolicy:
    """Get the global retry policy singleton."""
    global _retry_policy
    if _retry_policy is None:
        _retry_policy = RetryPolicy()
    return _retry_policy
