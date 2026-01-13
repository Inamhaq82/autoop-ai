from __future__ import annotations

import imaplib
import email
from email.header import decode_header
from typing import List, Optional

from autoops.products.lead_followup_v1.contracts import Lead, LeadSource, make_lead
from autoops.products.lead_followup_v1.normalizer import normalize_lead_text


def _decode_header_value(value: Optional[str]) -> str:
    if not value:
        return ""
    decoded, _enc = decode_header(value)[0]
    if isinstance(decoded, bytes):
        return decoded.decode(errors="replace")
    return str(decoded)


def _extract_text_plain(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition", "")).lower()
            if ctype == "text/plain" and "attachment" not in disp:
                payload = part.get_payload(decode=True) or b""
                return payload.decode(errors="replace")
        return ""
    payload = msg.get_payload(decode=True) or b""
    return payload.decode(errors="replace")


def fetch_unseen_imap(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    folder: str,
    max_results: int = 25,
) -> List[Lead]:
    """
    Read-only fetch of UNSEEN emails from a folder.
    Does NOT mark read, delete, or move messages.
    """
    leads: List[Lead] = []

    with imaplib.IMAP4_SSL(host, port) as imap:
        imap.login(username, password)

        status, _ = imap.select(folder)
        if status != "OK":
            raise RuntimeError(f"IMAP select failed for folder='{folder}'. Check folder name.")

        status, messages = imap.search(None, "UNSEEN")
        if status != "OK":
            return leads

        ids = messages[0].split()
        if not ids:
            return leads

        # Limit number of messages processed per run
        ids = ids[:max_results]

        for msg_id in ids:
            status, msg_data = imap.fetch(msg_id, "(RFC822)")
            if status != "OK":
                continue

            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            subject = _decode_header_value(msg.get("Subject", "")) or "(no subject)"
            from_addr = msg.get("From", "") or "unknown@email"

            body = _extract_text_plain(msg)
            cleaned = normalize_lead_text(body)

            lead = make_lead(
                source=LeadSource.EMAIL,
                from_address=from_addr,
                subject=subject,
                lead_text=cleaned,
                raw_ref=f"imap:{msg_id.decode(errors='replace')}",
            )
            leads.append(lead)

    return leads
