from __future__ import annotations

from typing import List, Optional
import requests
import msal

from autoops.products.lead_followup_v1.contracts import Lead, LeadSource, make_lead
from autoops.products.lead_followup_v1.normalizer import normalize_lead_text


GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def _get_token_device_code(
    client_id: str, scopes: list[str], tenant: str = "common"
) -> str:
    authority = f"https://login.microsoftonline.com/{tenant}"
    app = msal.PublicClientApplication(client_id=client_id, authority=authority)

    flow = app.initiate_device_flow(scopes=scopes)
    if "user_code" not in flow:
        raise RuntimeError(f"Failed to start device code flow: {flow}")

    # This prints the URL and code you paste into the browser
    print(flow["message"])

    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        raise RuntimeError(f"Token acquisition failed: {result}")
    return result["access_token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _find_mail_folder_id(token: str, folder_display_name: str) -> Optional[str]:
    # Start with top-level mail folders. If your folder is under Inbox,
    # we will also search Inbox child folders.
    r = requests.get(
        f"{GRAPH_BASE}/me/mailFolders?$top=200", headers=_headers(token), timeout=30
    )
    r.raise_for_status()
    folders = r.json().get("value", [])

    for f in folders:
        if f.get("displayName") == folder_display_name:
            return f.get("id")

    # Try Inbox children
    inbox_id = next(
        (f.get("id") for f in folders if f.get("displayName") == "Inbox"), None
    )
    if inbox_id:
        r = requests.get(
            f"{GRAPH_BASE}/me/mailFolders/{inbox_id}/childFolders?$top=200",
            headers=_headers(token),
            timeout=30,
        )
        r.raise_for_status()
        for f in r.json().get("value", []):
            if f.get("displayName") == folder_display_name:
                return f.get("id")

    return None


def fetch_recent_graph(
    *,
    client_id: str,
    scopes: list[str],
    folder_name: str,
    max_results: int = 25,
    tenant: str = "common",
    only_unread: bool = True,
) -> List[Lead]:
    """
    Fetch recent messages from a named folder using Microsoft Graph.
    Safe mode: does NOT mark read, move, or delete.
    """
    token = _get_token_device_code(client_id=client_id, scopes=scopes, tenant=tenant)

    folder_id = _find_mail_folder_id(token, folder_name)
    if not folder_id:
        raise RuntimeError(
            f"Folder '{folder_name}' not found. Ensure it exists in Outlook (under Inbox is OK)."
        )

    # Filter unread if desired
    filter_q = "&$filter=isRead eq false" if only_unread else ""

    url = (
        f"{GRAPH_BASE}/me/mailFolders/{folder_id}/messages"
        f"?$top={max_results}"
        f"&$select=id,subject,from,receivedDateTime,bodyPreview,isRead"
        f"{filter_q}"
        f"&$orderby=receivedDateTime desc"
    )

    r = requests.get(url, headers=_headers(token), timeout=30)
    r.raise_for_status()
    data = r.json()

    leads: List[Lead] = []
    for m in data.get("value", []):
        msg_id = m.get("id", "")
        subject = m.get("subject") or "(no subject)"
        received = m.get("receivedDateTime") or ""

        from_obj = m.get("from", {}).get("emailAddress", {})
        from_addr = from_obj.get("address") or "unknown@email"

        body_preview = m.get("bodyPreview") or ""
        cleaned = normalize_lead_text(body_preview)

        leads.append(
            make_lead(
                source=LeadSource.EMAIL,
                from_address=from_addr,
                subject=subject,
                lead_text=cleaned,
                raw_ref=f"graph:{msg_id}",
                received_at=received,
            )
        )
        msg_id = m.get("id", "")
        stable_lead_id = msg_id.replace("=", "").replace("+", "").replace("/", "")
        stable_lead_id = (
            stable_lead_id[-32:] if len(stable_lead_id) > 32 else stable_lead_id
        )

        lead = make_lead(
            lead_id=stable_lead_id,
            source=LeadSource.EMAIL,
            from_address=from_addr,
            subject=subject,
            lead_text=cleaned,
            raw_ref=f"graph:{msg_id}",
            received_at=received,
        )


def mark_read(token: str, msg_id: str) -> None:
    url = f"{GRAPH_BASE}/me/messages/{msg_id}"
    r = requests.patch(
        url,
        headers={**_headers(token), "Content-Type": "application/json"},
        json={"isRead": True},
        timeout=30,
    )
    r.raise_for_status()

    return leads
