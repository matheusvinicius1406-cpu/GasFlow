"""
Intent Contract — FASE 9

Structured intent representation for AI interactions.
Every user message is classified into an intent before tool execution.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from enum import Enum


class IntentType(str, Enum):
    CUSTOMER_LOOKUP = "CUSTOMER_LOOKUP"
    CUSTOMER_SEARCH = "CUSTOMER_SEARCH"
    CUSTOMER_SUMMARY = "CUSTOMER_SUMMARY"
    ORDER_LOOKUP = "ORDER_LOOKUP"
    ORDER_STATUS = "ORDER_STATUS"
    ORDER_CREATE = "ORDER_CREATE"
    PRODUCT_LOOKUP = "PRODUCT_LOOKUP"
    INVENTORY_LOOKUP = "INVENTORY_LOOKUP"
    INVENTORY_LOW_STOCK = "INVENTORY_LOW_STOCK"
    INVENTORY_SUMMARY = "INVENTORY_SUMMARY"
    PAYMENT_LOOKUP = "PAYMENT_LOOKUP"
    RECEIVABLE_LOOKUP = "RECEIVABLE_LOOKUP"
    FINANCIAL_SUMMARY = "FINANCIAL_SUMMARY"
    SALES_SUMMARY = "SALES_SUMMARY"
    GENERAL_QUESTION = "GENERAL_QUESTION"


class Confidence(str, Enum):
    HIGH = "HIGH"       # Can execute tool / respond
    MEDIUM = "MEDIUM"   # Ask for clarification
    LOW = "LOW"         # Do not execute


@dataclass
class Intent:
    type: IntentType
    confidence: Confidence
    entities: Dict[str, Any] = field(default_factory=dict)
    tool_name: Optional[str] = None
    tool_arguments: Dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = False
    reasoning: str = ""
    ambiguous_entities: List[str] = field(default_factory=list)
