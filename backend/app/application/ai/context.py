"""
Context Builder — FASE 9

Builds minimal, relevant context for the LLM per intent.
Never sends the entire database.
"""

from typing import Dict, Any, Optional, List
from app.domain.ai.intent import IntentType


class ContextBuilder:
    """Builds context for LLM based on intent type."""

    MAX_CONTEXT_TOKENS = 4000  # Rough limit

    def build(
        self,
        intent_type: IntentType,
        entities: Dict[str, Any],
        tool_results: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """Build context string for the LLM."""
        parts = []

        # Add conversation history (last 5 messages)
        if conversation_history:
            for msg in conversation_history[-5:]:
                role = msg.get("role", "user")
                content = msg.get("content", "")[:500]
                parts.append(f"[{role}]: {content}")

        # Add tool results if available
        if tool_results:
            parts.append(f"[DADOS]: {self._format_results(tool_results)}")

        # Add entity context
        if entities:
            entity_str = ", ".join(f"{k}={v}" for k, v in entities.items() if v)
            if entity_str:
                parts.append(f"[ENTIDADES]: {entity_str}")

        context = "\n".join(parts)

        # Truncate if too long (rough: 4 chars per token)
        if len(context) > self.MAX_CONTEXT_TOKENS * 4:
            context = context[:self.MAX_CONTEXT_TOKENS * 4] + "\n[...]"

        return context

    def _format_results(self, results: Dict[str, Any]) -> str:
        """Format tool results into readable context."""
        lines = []
        for key, value in results.items():
            if isinstance(value, dict):
                for k, v in value.items():
                    lines.append(f"  {k}: {v}")
            elif isinstance(value, list):
                lines.append(f"  {key}: {len(value)} itens")
                for item in value[:5]:
                    if isinstance(item, dict):
                        summary = ", ".join(f"{k}={v}" for k, v in list(item.items())[:3])
                        lines.append(f"    - {summary}")
            else:
                lines.append(f"  {key}: {value}")
        return "\n".join(lines)
