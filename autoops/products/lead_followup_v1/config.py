from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class V1Config:
    # Ingestion (file-drop)
    inbox_dir: Path
    processed_dir: Path

    # State
    data_dir: Path
    leads_jsonl: Path

    # Behavior
    dry_run: bool
    reply_tone: str
    signature: str
    alert_to: str | None

    # SMTP (optional)
    smtp_host: str | None
    smtp_port: int
    smtp_user: str | None
    smtp_pass: str | None
    smtp_from: str | None

    # Input selection
    input_mode: str  # "file" or "email"

    # IMAP (optional)
    imap_enabled: bool
    imap_host: str | None
    imap_port: int
    imap_user: str | None
    imap_pass: str | None
    imap_folder: str

    # Email provider selection
    email_provider: str  # "imap" or "graph"

    # Microsoft Graph (optional)
    graph_enabled: bool
    graph_client_id: str | None
    graph_tenant: str
    graph_scopes: str
    graph_folder: str



def load_config() -> V1Config:
    root = Path(os.getenv("AUTOOPS_ROOT", str(Path.cwd())))

    # File-drop input
    inbox_dir = Path(os.getenv("V1_INBOX_DIR", str(root / "inbox_drop")))
    processed_dir = Path(os.getenv("V1_PROCESSED_DIR", str(inbox_dir / "processed")))

    # State
    data_dir = Path(os.getenv("V1_DATA_DIR", str(root / "data")))
    leads_jsonl = Path(os.getenv("V1_LEADS_JSONL", str(data_dir / "leads_v1.jsonl")))

    # Behavior
    dry_run = os.getenv("V1_DRY_RUN", "1").strip() == "1"
    reply_tone = os.getenv("V1_REPLY_TONE", "professional").strip()
    signature = os.getenv("V1_SIGNATURE", "Automation-AI").strip()
    alert_to = os.getenv("V1_ALERT_TO", "").strip() or None

    # SMTP
    smtp_host = os.getenv("V1_SMTP_HOST", "").strip() or None
    smtp_port = int(os.getenv("V1_SMTP_PORT", "587").strip() or "587")
    smtp_user = os.getenv("V1_SMTP_USER", "").strip() or None
    smtp_pass = os.getenv("V1_SMTP_PASS", "").strip() or None
    smtp_from = os.getenv("V1_FROM_ADDR", "").strip() or None

    email_provider = os.getenv("V1_EMAIL_PROVIDER", "imap").strip().lower()

    graph_enabled = os.getenv("V1_GRAPH_ENABLED", "0").strip() == "1"
    graph_client_id = os.getenv("V1_GRAPH_CLIENT_ID", "").strip() or None
    graph_tenant = os.getenv("V1_GRAPH_TENANT", "common").strip() or "common"
    graph_scopes = os.getenv("V1_GRAPH_SCOPES", "Mail.Read").strip() or "Mail.Read"
    graph_folder = os.getenv("V1_GRAPH_FOLDER", "Automation-AI-Test").strip() or "Automation-AI-Test"

    # Input selection
    input_mode = os.getenv("V1_INPUT", "file").strip().lower()

    # IMAP
    imap_enabled = os.getenv("V1_IMAP_ENABLED", "0").strip() == "1"
    imap_host = os.getenv("V1_IMAP_HOST", "").strip() or None
    imap_port = int(os.getenv("V1_IMAP_PORT", "993").strip() or "993")
    imap_user = os.getenv("V1_IMAP_USER", "").strip() or None
    imap_pass = os.getenv("V1_IMAP_PASS", "").strip() or None
    imap_folder = os.getenv("V1_IMAP_FOLDER", "Automation-AI-Test").strip() or "Automation-AI-Test"

    return V1Config(
        inbox_dir=inbox_dir,
        processed_dir=processed_dir,
        data_dir=data_dir,
        leads_jsonl=leads_jsonl,

        dry_run=dry_run,
        reply_tone=reply_tone,
        signature=signature,
        alert_to=alert_to,

        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_user=smtp_user,
        smtp_pass=smtp_pass,
        smtp_from=smtp_from,

        input_mode=input_mode,

        imap_enabled=imap_enabled,
        imap_host=imap_host,
        imap_port=imap_port,
        imap_user=imap_user,
        imap_pass=imap_pass,
        imap_folder=imap_folder,

        email_provider=email_provider,

        graph_enabled=graph_enabled,
        graph_client_id=graph_client_id,
        graph_tenant=graph_tenant,
        graph_scopes=graph_scopes,
        graph_folder=graph_folder,

    )
