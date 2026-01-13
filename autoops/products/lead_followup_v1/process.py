from __future__ import annotations

from autoops.products.lead_followup_v1.config import load_config
from autoops.products.lead_followup_v1.state.store import read_leads_jsonl
from autoops.products.lead_followup_v1.actions.classify import classify_urgency
from autoops.products.lead_followup_v1.actions.reply import build_reply
from autoops.products.lead_followup_v1.actions.log_excel import append_lead
from autoops.products.lead_followup_v1.actions.deliver import (
    send_reply,
    send_urgent_alert,
)


def main() -> int:
    cfg = load_config()

    leads = list(read_leads_jsonl(cfg.leads_jsonl))
    if not leads:
        print(f"[V1] No leads found at {cfg.leads_jsonl}")
        return 0

    excel_path = cfg.data_dir / "leads_v1.xlsx"

    # Prefer config-driven values (safe defaults)
    tone = getattr(cfg, "reply_tone", "professional") or "professional"
    signature = getattr(cfg, "signature", "Automation-AI") or "Automation-AI"

    # For FILE leads, we cannot reply to unknown@filedrop
    fallback_to = getattr(cfg, "alert_to", None)

    for lead in leads:
        urgency = classify_urgency(lead)
        reply_body = build_reply(
            lead,
            tone=tone,
            signature=signature,
        )

        # Log FIRST (audit trail even if delivery fails)
        added = append_lead(
            excel_path,
            lead,
            urgency,
            status="REPLIED_DRAFTED",
        )

        if not added:
            print(f"[V1] Skipping duplicate lead_id={lead.lead_id}")
            continue

        # Decide reply destination
        reply_to = lead.from_address
        if lead.source.value == "file":
            if not fallback_to:
                print(
                    f"[V1] No V1_ALERT_TO set; "
                    f"skipping reply send for file lead {lead.lead_id}"
                )
                reply_to = None
            else:
                reply_to = fallback_to

        # Send reply (DRY_RUN-safe)
        if reply_to:
            send_reply(
                cfg=cfg,
                lead=lead,
                reply_to=reply_to,
                urgency=urgency,
            )

        # Send urgent alert if needed (DRY_RUN-safe)
        send_urgent_alert(
            cfg=cfg,
            lead=lead,
            urgency=urgency,
        )

        print(
            f"[V1] processed lead_id={lead.lead_id} "
            f"urgency={urgency.value} subject={lead.subject}"
        )
        print(
            "----- reply preview -----\n"
            f"{reply_body[:300]}\n"
            "-------------------------\n"
        )

    print(f"[V1][DEBUG] from_address={lead.from_address} source={lead.source.value} raw_ref={lead.raw_ref}")

    print(f"[V1] Excel updated: {excel_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
