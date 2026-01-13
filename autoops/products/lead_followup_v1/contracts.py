"""
contracts.py

V1 "paid offer" contracts for Automation-AI Lead Intake & Auto-Follow-Up.

Design goals:
- Deterministic, minimal fields (no scope creep)
- Safe defaults so adapters can be dumb
- Easy to serialize to JSONL and replay later
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from uuid import uuid4


# ----------------------------
# Enums (tight, stable)
# ----------------------------

class LeadSource(str, Enum):
    EMAIL = "email"
    FILE = "file"
    FORM = "form"     # keep for later, not used Day 3
    API = "api"       # keep for later, not used Day 3


class UrgencyLabel(str, Enum):
    UNKNOWN = "UNKNOWN"  # Day 3 default
    LOW = "LOW"
    NORMAL = "NORMAL"
    URGENT = "URGENT"


# ----------------------------
# Helpers
# ----------------------------

def now_iso_utc() -> str:
    """ISO-8601 timestamp in UTC with 'Z' suffix."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_lead_id() -> str:
    """Generate a stable unique id for lead objects."""
    return uuid4().hex


def _require_non_empty(value: str, field_name: str, max_len: int | None = None) -> str:
    if value is None:
        raise ValueError(f"{field_name} is required (got None)")
    s = str(value).strip()
    if not s:
        raise ValueError(f"{field_name} is required (got empty)")
    if max_len is not None and len(s) > max_len:
        raise ValueError(f"{field_name} exceeds max length {max_len} (len={len(s)})")
    return s


def _optional_str(value: Optional[str], max_len: int | None = None) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if max_len is not None and len(s) > max_len:
        return s[:max_len]
    return s


# ----------------------------
# Core Contract: Lead
# ----------------------------

@dataclass(frozen=True)
class Lead:
    """
    Minimal normalized representation of an inbound lead.

    This is the single source of truth for the v1 pipeline.
    Adapters MUST output this shape; downstream MUST consume it.
    """

    # Identity / traceability
    lead_id: str
    source: LeadSource
    received_at: str

    # Sender/context
    from_address: str
    subject: str

    # The cleaned content we will classify/reply from
    lead_text: str

    # Reference to the raw input (message-id, file path, webhook id)
    raw_ref: str

    # Optional fields (keep tiny to avoid scope creep)
    urgency: UrgencyLabel = UrgencyLabel.UNKNOWN
    client_id: Optional[str] = None  # if you later support multiple clients

    def __post_init__(self) -> None:
        # Validate required fields (tight limits prevent weird payloads)
        _require_non_empty(self.lead_id, "lead_id", max_len=64)
        _require_non_empty(self.received_at, "received_at", max_len=32)
        _require_non_empty(self.from_address, "from_address", max_len=256)
        _require_non_empty(self.subject, "subject", max_len=500)
        _require_non_empty(self.lead_text, "lead_text", max_len=20000)
        _require_non_empty(self.raw_ref, "raw_ref", max_len=500)

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize to JSON-safe dict for JSONL logging.
        Enums become strings.
        """
        d = asdict(self)
        d["source"] = self.source.value
        d["urgency"] = self.urgency.value
        return d

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Lead":
        """
        Deserialize from JSON dict (e.g., replay from JSONL).
        """
        return Lead(
            lead_id=_require_non_empty(d.get("lead_id", ""), "lead_id"),
            source=LeadSource(_require_non_empty(d.get("source", ""), "source")),
            received_at=_require_non_empty(d.get("received_at", ""), "received_at"),
            from_address=_require_non_empty(d.get("from_address", ""), "from_address"),
            subject=_require_non_empty(d.get("subject", ""), "subject"),
            lead_text=_require_non_empty(d.get("lead_text", ""), "lead_text"),
            raw_ref=_require_non_empty(d.get("raw_ref", ""), "raw_ref"),
            urgency=UrgencyLabel(d.get("urgency", UrgencyLabel.UNKNOWN.value)),
            client_id=_optional_str(d.get("client_id")),
        )


# ----------------------------
# Factory functions
# ----------------------------

def make_lead(
    *,
    source: LeadSource,
    from_address: str,
    subject: str,
    lead_text: str,
    raw_ref: str,
    received_at: Optional[str] = None,
    lead_id: Optional[str] = None,
    urgency: UrgencyLabel = UrgencyLabel.UNKNOWN,
    client_id: Optional[str] = None,
) -> Lead:

    lead_id = lead_id or uuid4().hex
    """
    The ONLY recommended way for adapters to create Lead objects.
    Provides sane defaults and prevents partially-initialized objects.
    """
    return Lead(
        lead_id=lead_id or new_lead_id(),
        source=source,
        received_at=received_at or now_iso_utc(),
        from_address=_require_non_empty(from_address, "from_address", max_len=256),
        subject=_require_non_empty(subject, "subject", max_len=500),
        lead_text=_require_non_empty(lead_text, "lead_text", max_len=20000),
        raw_ref=_require_non_empty(raw_ref, "raw_ref", max_len=500),
        urgency=urgency,
        client_id=_optional_str(client_id),
    )
