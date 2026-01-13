from __future__ import annotations

from pathlib import Path
from typing import List

from autoops.products.lead_followup_v1.contracts import LeadSource, make_lead, Lead
from autoops.products.lead_followup_v1.normalizer import normalize_lead_text

SUPPORTED_EXTS = {".txt"}  # keep v1 simple

def list_inbox_files(inbox_dir: Path) -> List[Path]:
    inbox_dir.mkdir(parents=True, exist_ok=True)
    return sorted(
        [p for p in inbox_dir.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS]
    )

def ingest_file(path: Path) -> Lead:
    raw = path.read_text(encoding="utf-8", errors="replace")

    # Optional: treat first line as subject if it starts with "Subject:"
    subject = "(no subject)"
    body = raw
    lines = raw.splitlines()
    if lines and lines[0].lower().startswith("subject:"):
        subject = lines[0].split(":", 1)[1].strip() or "(no subject)"
        body = "\n".join(lines[1:])

    cleaned = normalize_lead_text(body)

    # Minimal from_address in file-drop mode
    from_address = "unknown@filedrop"

    return make_lead(
        source=LeadSource.FILE,
        from_address=from_address,
        subject=subject,
        lead_text=cleaned,
        raw_ref=str(path),
    )

def move_to_processed(src: Path, processed_dir: Path) -> Path:
    processed_dir.mkdir(parents=True, exist_ok=True)
    dst = processed_dir / src.name
    # If file already exists, create a unique name
    if dst.exists():
        dst = processed_dir / f"{src.stem}_{src.stat().st_mtime_ns}{src.suffix}"
    src.rename(dst)
    return dst
