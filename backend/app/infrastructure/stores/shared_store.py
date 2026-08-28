"""
Shared In-Memory Store

Single source of truth for driver, delivery, vehicle, and session data.
Used by both driver_api.py and delivery_ops.py.

This eliminates the P0 bug where drivers created via admin were invisible
to the driver login system.
"""

import threading
from typing import Any, Dict


_store: Dict[str, Any] = {}
_lock = threading.Lock()


def get_shared_store() -> Dict[str, Any]:
    """Get the shared in-memory store (singleton)."""
    with _lock:
        if "drivers" not in _store:
            _store["drivers"] = {}
        if "deliveries" not in _store:
            _store["deliveries"] = {}
        if "vehicles" not in _store:
            _store["vehicles"] = {}
        if "routes" not in _store:
            _store["routes"] = {}
        if "sessions" not in _store:
            _store["sessions"] = {}
        if "idempotency_keys" not in _store:
            _store["idempotency_keys"] = set()
        if "locations" not in _store:
            _store["locations"] = {}
        if "proofs" not in _store:
            _store["proofs"] = {}
    return _store


def clear_store():
    """Clear all data (for testing)."""
    with _lock:
        _store.clear()
