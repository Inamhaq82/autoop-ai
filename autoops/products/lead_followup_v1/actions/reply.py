from __future__ import annotations

from autoops.products.lead_followup_v1.contracts import Lead

TEMPLATES = {
    "professional": (
        "Hello,\n\n"
        "Thanks for reaching out — we’ve received your message and are reviewing it now.\n"
        "If you can share any additional details (timing, screenshots, or key requirements), it will help us respond faster.\n\n"
        "Best regards,\n"
        "{signature}\n"
    ),
    "friendly": (
        "Hi there,\n\n"
        "Thanks for reaching out! We got your message and we’re taking a look now.\n"
        "If you can share a bit more detail (timing, screenshots, what you’re trying to achieve), we can move faster.\n\n"
        "Thanks,\n"
        "{signature}\n"
    ),
    "direct": (
        "Received — thank you.\n\n"
        "We’re reviewing this now. If you can send key details (deadline, screenshots, requirements), we’ll respond faster.\n\n"
        "- {signature}\n"
    ),
}

def build_reply(lead: Lead, tone: str = "professional", signature: str = "Automation-AI Team") -> str:
    tone_key = (tone or "professional").strip().lower()
    if tone_key not in TEMPLATES:
        tone_key = "professional"
    return TEMPLATES[tone_key].format(signature=signature)
