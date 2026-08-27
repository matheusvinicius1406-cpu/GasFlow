"""
LLM Provider Abstraction — FASE 9

Provider-agnostic interface for LLM interactions.
Domain never imports Gemini/OpenAI/etc directly.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum


class LLMRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class LLMMessage:
    role: LLMRole
    content: str


@dataclass
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    latency_ms: float = 0.0


@dataclass
class LLMResponse:
    content: str
    usage: LLMUsage = field(default_factory=LLMUsage)
    finish_reason: str = "stop"
    error: Optional[str] = None


class LLMProvider(ABC):
    """Abstract LLM provider interface."""

    @abstractmethod
    def generate(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """Generate a text response from messages."""
        ...

    @abstractmethod
    def generate_structured(
        self,
        messages: List[LLMMessage],
        schema: Dict[str, Any],
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Generate a structured JSON response matching schema."""
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """Check if provider is available."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the model identifier."""
        ...
