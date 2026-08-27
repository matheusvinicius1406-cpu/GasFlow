"""
Tool System — FASE 9

Registry of AI tools with schema validation and permission checks.
Tools call Application Use Cases, never repositories directly.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from enum import Enum


class ToolPermission(str, Enum):
    READ_ONLY = "READ_ONLY"
    OPERATOR = "OPERATOR"
    ADMIN = "ADMIN"


class ToolType(str, Enum):
    READ = "READ"
    WRITE = "WRITE"


@dataclass
class ToolDefinition:
    name: str
    description: str
    tool_type: ToolType
    permission: ToolPermission
    input_schema: Dict[str, Any]  # JSON Schema for validation
    requires_confirmation: bool = False
    handler: Optional[Callable] = None


@dataclass
class ToolResult:
    success: bool
    data: Any = None
    error: Optional[str] = None
    display_message: str = ""


class ToolRegistry:
    """Registry of available AI tools."""

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition):
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def list_tools(self) -> List[ToolDefinition]:
        return list(self._tools.values())

    def list_readable(self) -> List[ToolDefinition]:
        return [t for t in self._tools.values() if t.tool_type == ToolType.READ]

    def list_writable(self) -> List[ToolDefinition]:
        return [t for t in self._tools.values() if t.tool_type == ToolType.WRITE]

    def validate_input(self, tool_name: str, arguments: Dict[str, Any]) -> List[str]:
        """Validate arguments against tool's input schema. Returns list of errors."""
        tool = self.get(tool_name)
        if not tool:
            return [f"Tool '{tool_name}' not found"]
        errors = []
        schema = tool.input_schema
        required = schema.get("required", [])
        properties = schema.get("properties", {})
        for field_name in required:
            if field_name not in arguments:
                errors.append(f"Missing required field: {field_name}")
        for key, value in arguments.items():
            if key in properties:
                prop = properties[key]
                expected_type = prop.get("type")
                if expected_type == "string" and not isinstance(value, str):
                    errors.append(f"Field '{key}' must be string")
                elif expected_type == "number" and not isinstance(value, (int, float)):
                    errors.append(f"Field '{key}' must be number")
                elif expected_type == "integer" and not isinstance(value, int):
                    errors.append(f"Field '{key}' must be integer")
        return errors
