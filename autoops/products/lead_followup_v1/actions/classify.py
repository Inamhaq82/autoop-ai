from __future__ import annotations

from autoops.products.lead_followup_v1.contracts import Lead, UrgencyLabel

URGENT_KEYWORDS = [
    "urgent", "asap", "immediately", "today", "right away",
    "down", "outage", "broken", "can't access", "cannot access",
    "payment failed", "failed payment", "error", "deadline"
]

def classify_urgency(lead: Lead) -> UrgencyLabel:
    text = (lead.subject + "\n" + lead.lead_text).lower()
    for kw in URGENT_KEYWORDS:
        if kw in text:
            return UrgencyLabel.URGENT
    return UrgencyLabel.NORMAL
