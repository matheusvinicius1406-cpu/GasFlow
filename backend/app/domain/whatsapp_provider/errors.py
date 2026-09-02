"""
WhatsApp Provider Error Normalization — WAVE 2

Common errors across all providers.
Provider adapters translate provider-specific errors to these.
"""

from enum import Enum


class WhatsAppErrorType(str, Enum):
    """Normalized error types."""
    CONNECTION_ERROR = "connection_error"
    AUTHENTICATION_ERROR = "authentication_error"
    SEND_ERROR = "send_error"
    MEDIA_ERROR = "media_error"
    RATE_LIMIT_ERROR = "rate_limit_error"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    SESSION_LOST = "session_lost"
    QR_EXPIRED = "qr_expired"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


class WhatsAppError(Exception):
    """Base WhatsApp provider error."""

    def __init__(
        self,
        message: str,
        error_type: WhatsAppErrorType = WhatsAppErrorType.UNKNOWN,
        provider: str = "unknown",
        retryable: bool = False,
        raw_error: Exception | None = None,
    ):
        super().__init__(message)
        self.error_type = error_type
        self.provider = provider
        self.retryable = retryable
        self.raw_error = raw_error

    def to_dict(self) -> dict:
        return {
            "error_type": self.error_type.value,
            "message": str(self),
            "provider": self.provider,
            "retryable": self.retryable,
        }


class WhatsAppConnectionError(WhatsAppError):
    """Connection to WhatsApp failed."""
    def __init__(self, message: str, provider: str = "unknown", retryable: bool = True, **kwargs):
        super().__init__(message, WhatsAppErrorType.CONNECTION_ERROR, provider, retryable, **kwargs)


class WhatsAppAuthError(WhatsAppError):
    """Authentication failed."""
    def __init__(self, message: str, provider: str = "unknown", **kwargs):
        super().__init__(message, WhatsAppErrorType.AUTHENTICATION_ERROR, provider, retryable=False, **kwargs)


class WhatsAppSendError(WhatsAppError):
    """Message send failed."""
    def __init__(self, message: str, provider: str = "unknown", retryable: bool = True, **kwargs):
        super().__init__(message, WhatsAppErrorType.SEND_ERROR, provider, retryable, **kwargs)


class WhatsAppMediaError(WhatsAppError):
    """Media handling failed."""
    def __init__(self, message: str, provider: str = "unknown", retryable: bool = False, **kwargs):
        super().__init__(message, WhatsAppErrorType.MEDIA_ERROR, provider, retryable, **kwargs)


class WhatsAppRateLimitError(WhatsAppError):
    """Rate limited by WhatsApp."""
    def __init__(self, message: str, provider: str = "unknown", retry_after: int = 60, **kwargs):
        super().__init__(message, WhatsAppErrorType.RATE_LIMIT_ERROR, provider, retryable=True, **kwargs)
        self.retry_after = retry_after


class WhatsAppProviderUnavailable(WhatsAppError):
    """Provider is not available."""
    def __init__(self, message: str, provider: str = "unknown", **kwargs):
        super().__init__(message, WhatsAppErrorType.PROVIDER_UNAVAILABLE, provider, retryable=True, **kwargs)


class WhatsAppSessionLost(WhatsAppError):
    """Session was lost."""
    def __init__(self, message: str, provider: str = "unknown", **kwargs):
        super().__init__(message, WhatsAppErrorType.SESSION_LOST, provider, retryable=True, **kwargs)


class WhatsAppTimeoutError(WhatsAppError):
    """Operation timed out."""
    def __init__(self, message: str, provider: str = "unknown", **kwargs):
        super().__init__(message, WhatsAppErrorType.TIMEOUT, provider, retryable=True, **kwargs)
