from __future__ import annotations

from autoops.products.lead_followup_v1.contracts import Lead, UrgencyLabel
from autoops.products.lead_followup_v1.actions.reply import build_reply
from autoops.products.lead_followup_v1.actions.emailer import send_email_smtp


def send_reply(
    *,
    cfg,
    lead: Lead,
    reply_to: str,
    urgency: UrgencyLabel,
) -> None:
    subject = f"Re: {lead.subject}"
    body = build_reply(lead, tone=cfg.reply_tone, signature=cfg.signature)

    if cfg.dry_run:
        print(f"[V1][DRY_RUN] Would send REPLY to={reply_to} subject={subject}")
        return

    _require_smtp(cfg)
    send_email_smtp(
        smtp_host=cfg.smtp_host,
        smtp_port=cfg.smtp_port,
        username=cfg.smtp_user,
        password=cfg.smtp_pass,
        from_addr=cfg.smtp_from,
        to_addr=reply_to,
        subject=subject,
        body=body,
    )


def send_urgent_alert(*, cfg, lead: Lead, urgency: UrgencyLabel) -> None:
    if urgency != UrgencyLabel.URGENT:
        return
    if not cfg.alert_to:
        print("[V1] No V1_ALERT_TO set; skipping urgent alert.")
        return

    subject = f"[URGENT] Lead needs attention: {lead.subject}"
    body = (
        "An urgent lead was detected.\n\n"
        f"From: {lead.from_address}\n"
        f"Subject: {lead.subject}\n"
        f"Received: {lead.received_at}\n"
        f"Lead ID: {lead.lead_id}\n"
        f"Raw Ref: {lead.raw_ref}\n\n"
        "Next step: review and respond manually if needed.\n"
    )

    if cfg.dry_run:
        print(f"[V1][DRY_RUN] Would send URGENT ALERT to={cfg.alert_to} subject={subject}")
        return

    _require_smtp(cfg)
    send_email_smtp(
        smtp_host=cfg.smtp_host,
        smtp_port=cfg.smtp_port,
        username=cfg.smtp_user,
        password=cfg.smtp_pass,
        from_addr=cfg.smtp_from,
        to_addr=cfg.alert_to,
        subject=subject,
        body=body,
    )


def _require_smtp(cfg) -> None:
    missing = []
    for k in ["smtp_host", "smtp_user", "smtp_pass", "smtp_from"]:
        if getattr(cfg, k) in (None, ""):
            missing.append(k)
    if missing:
        raise RuntimeError(f"SMTP config missing: {missing}. Set env vars or use V1_DRY_RUN=1.")
