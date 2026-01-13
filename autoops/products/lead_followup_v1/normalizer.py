from __future__ import annotations
import re

MAX_LEN = 4000

def normalize_lead_text(text: str) -> str:
    if not text:
        return ""

    # Normalize line endings & strip whitespace
    t = text.replace("\r\n", "\n").replace("\r", "\n").strip()

    # Remove quoted email lines (simple heuristic)
    lines = []
    for line in t.split("\n"):
        if line.strip().startswith(">"):
            continue
        lines.append(line)
    t = "\n".join(lines).strip()

    # Remove excessive blank lines
    t = re.sub(r"\n{3,}", "\n\n", t)

    # Hard truncate (protect future LLM calls)
    if len(t) > MAX_LEN:
        t = t[:MAX_LEN].rstrip() + "\n\n[TRUNCATED]"

    return t
