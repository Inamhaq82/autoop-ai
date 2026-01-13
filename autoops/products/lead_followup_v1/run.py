from __future__ import annotations

from autoops.products.lead_followup_v1.config import load_config
from autoops.products.lead_followup_v1.adapters.file_drop import (
    list_inbox_files,
    ingest_file,
    move_to_processed,
)
from autoops.products.lead_followup_v1.adapters.email_graph import fetch_recent_graph
from autoops.products.lead_followup_v1.state.store import append_leads_jsonl


def main() -> int:
    cfg = load_config()

    cfg.processed_dir.mkdir(parents=True, exist_ok=True)
    cfg.data_dir.mkdir(parents=True, exist_ok=True)

    input_mode = (getattr(cfg, "input_mode", "file") or "file").lower()

    leads = []

    if input_mode == "email":
        provider = (getattr(cfg, "email_provider", "imap") or "imap").lower()

        if provider == "graph":
            if not getattr(cfg, "graph_enabled", False):
                raise RuntimeError(
                    "V1_EMAIL_PROVIDER=graph but V1_GRAPH_ENABLED is not set to 1."
                )

            if not getattr(cfg, "graph_client_id", None):
                raise RuntimeError(
                    "Missing V1_GRAPH_CLIENT_ID. Create an Azure App Registration and set it."
                )

            scopes = [
                s.strip()
                for s in (cfg.graph_scopes or "Mail.Read").split()
                if s.strip()
            ]
            folder = (
                getattr(cfg, "graph_folder", "Automation-AI-Test")
                or "Automation-AI-Test"
            )

            leads = fetch_recent_graph(
                client_id=cfg.graph_client_id,
                tenant=cfg.graph_tenant or "common",
                scopes=scopes,
                folder_name=folder,
                max_results=25,
                only_unread=True,
            )

            if not leads:
                print(f"[V1] No new unread emails in folder '{folder}' (Graph)")
                return 0

            written = append_leads_jsonl(cfg.leads_jsonl, leads)
            print(f"[V1] Appended {written} email lead(s) to {cfg.leads_jsonl} (Graph)")
            return 0

        # fallback: IMAP (may fail on Outlook due to BasicAuthBlocked)
        if not getattr(cfg, "imap_enabled", False):
            raise RuntimeError("V1_INPUT=email but V1_IMAP_ENABLED is not set to 1.")

        missing = []
        for name in ["imap_host", "imap_user", "imap_pass"]:
            if not getattr(cfg, name, None):
                missing.append(name)
        if missing:
            raise RuntimeError(
                f"Missing IMAP config: {missing}. Set env vars or switch V1_INPUT=file."
            )

        leads = fetch_unseen_imap(
            host=cfg.imap_host,
            port=cfg.imap_port,
            username=cfg.imap_user,
            password=cfg.imap_pass,
            folder=cfg.imap_folder,
            max_results=25,
        )

        if not leads:
            print(f"[V1] No new unseen emails in folder '{cfg.imap_folder}' (IMAP)")
            return 0

        written = append_leads_jsonl(cfg.leads_jsonl, leads)
        print(f"[V1] Appended {written} email lead(s) to {cfg.leads_jsonl} (IMAP)")
        return 0

    # Default: file input
    inbox_files = list_inbox_files(cfg.inbox_dir)
    if not inbox_files:
        print(f"[V1] No new files in {cfg.inbox_dir}")
        return 0

    for f in inbox_files:
        lead = ingest_file(f)
        leads.append(lead)
        moved = move_to_processed(f, cfg.processed_dir)
        print(f"[V1] Ingested lead_id={lead.lead_id} moved={moved.name}")

    written = append_leads_jsonl(cfg.leads_jsonl, leads)
    print(f"[V1] Appended {written} lead(s) to {cfg.leads_jsonl}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
