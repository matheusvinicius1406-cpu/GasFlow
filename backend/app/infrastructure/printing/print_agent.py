"""
Print Agent — GasFlow

Manages print jobs, printer status, and history.
Designed to work with a local print agent service
that communicates with physical ESC/POS printers.

Architecture:
    Backend API → Print Agent → Printer Transport → GT710

The print agent can operate in two modes:
1. Direct mode: generates ESC/POS bytes for external delivery
2. Agent mode: communicates with a local print agent service
"""

import threading
import time
from typing import Any, Dict, List, Optional
from datetime import datetime
from enum import Enum

from app.infrastructure.printing.escpos import ReceiptFormatter


class PrinterStatus(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    ERROR = "ERROR"
    PAPER_UNKNOWN = "PAPER_UNKNOWN"
    NOT_CONFIGURED = "NOT_CONFIGURED"


class PrintJobStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class PrintJob:
    """Represents a print job."""

    def __init__(
        self,
        order_id: str,
        tenant_id: str,
        order_data: Dict[str, Any],
        requested_by: str = "",
        is_reprint: bool = False,
    ):
        self.id = f"print-{order_id}-{int(time.time() * 1000)}"
        self.order_id = order_id
        self.tenant_id = tenant_id
        self.order_data = order_data
        self.requested_by = requested_by
        self.is_reprint = is_reprint
        self.status = PrintJobStatus.PENDING
        self.created_at = datetime.utcnow().isoformat()
        self.completed_at: Optional[str] = None
        self.error: Optional[str] = None
        self.escpos_data: Optional[bytes] = None
        self.attempts = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "order_id": self.order_id,
            "tenant_id": self.tenant_id,
            "requested_by": self.requested_by,
            "is_reprint": self.is_reprint,
            "status": self.status.value,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "attempts": self.attempts,
        }


class PrintAgent:
    """
    Manages print jobs and printer status.

    In production, this would communicate with a local print agent service
    that has direct USB access to the printer. For now, it generates
    ESC/POS data that can be sent via any transport.
    """

    def __init__(self):
        self._jobs: Dict[str, PrintJob] = {}
        self._lock = threading.Lock()
        self._printer_status = PrinterStatus.NOT_CONFIGURED
        self._formatter = ReceiptFormatter()
        self._auto_print_enabled = False

    @property
    def printer_status(self) -> PrinterStatus:
        return self._printer_status

    @printer_status.setter
    def printer_status(self, status: PrinterStatus):
        self._printer_status = status

    @property
    def auto_print_enabled(self) -> bool:
        return self._auto_print_enabled

    @auto_print_enabled.setter
    def auto_print_enabled(self, enabled: bool):
        self._auto_print_enabled = enabled

    def create_print_job(
        self,
        order_id: str,
        tenant_id: str,
        order_data: Dict[str, Any],
        requested_by: str = "",
        is_reprint: bool = False,
    ) -> PrintJob:
        """Create a new print job."""
        job = PrintJob(
            order_id=order_id,
            tenant_id=tenant_id,
            order_data=order_data,
            requested_by=requested_by,
            is_reprint=is_reprint,
        )

        # Generate ESC/POS data
        try:
            job.escpos_data = self._formatter.format_order(order_data)
            job.status = PrintJobStatus.PENDING
        except Exception as e:
            job.status = PrintJobStatus.FAILED
            job.error = str(e)

        with self._lock:
            self._jobs[job.id] = job

        return job

    def get_job(self, job_id: str) -> Optional[PrintJob]:
        """Get a print job by ID."""
        return self._jobs.get(job_id)

    def get_jobs_for_order(self, order_id: str, tenant_id: str) -> List[PrintJob]:
        """Get all print jobs for a specific order."""
        return [j for j in self._jobs.values() if j.order_id == order_id and j.tenant_id == tenant_id]

    def get_jobs_for_tenant(self, tenant_id: str, limit: int = 50) -> List[PrintJob]:
        """Get recent print jobs for a tenant."""
        jobs = [j for j in self._jobs.values() if j.tenant_id == tenant_id]
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs[:limit]

    def complete_job(self, job_id: str, success: bool = True, error: str = "") -> bool:
        """Mark a print job as completed or failed."""
        job = self._jobs.get(job_id)
        if not job:
            return False

        with self._lock:
            if success:
                job.status = PrintJobStatus.COMPLETED
            else:
                job.status = PrintJobStatus.FAILED
                job.error = error
            job.completed_at = datetime.utcnow().isoformat()
            job.attempts += 1

        return True

    def get_printer_status(self) -> Dict[str, Any]:
        """Get current printer status."""
        return {
            "status": self._printer_status.value,
            "auto_print_enabled": self._auto_print_enabled,
            "pending_jobs": sum(1 for j in self._jobs.values() if j.status == PrintJobStatus.PENDING),
            "total_jobs_today": len(
                [
                    j
                    for j in self._jobs.values()
                    if j.created_at and j.created_at[:10] == datetime.utcnow().strftime("%Y-%m-%d")
                ]
            ),
        }

    def set_printer_online(self):
        """Set printer status to online."""
        self._printer_status = PrinterStatus.ONLINE

    def set_printer_offline(self):
        """Set printer status to offline."""
        self._printer_status = PrinterStatus.OFFLINE

    def set_printer_error(self, error: str = ""):
        """Set printer status to error."""
        self._printer_status = PrinterStatus.ERROR


# Singleton instance
_print_agent: Optional[PrintAgent] = None
_print_agent_lock = threading.Lock()


def get_print_agent() -> PrintAgent:
    """Get the singleton print agent instance."""
    global _print_agent
    with _print_agent_lock:
        if _print_agent is None:
            _print_agent = PrintAgent()
        return _print_agent
