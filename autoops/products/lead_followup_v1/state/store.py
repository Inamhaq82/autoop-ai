from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable
from autoops.products.lead_followup_v1.contracts import Lead

def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

def append_leads_jsonl(path: Path, leads: Iterable[Lead]) -> int:
    ensure_parent(path)
    count = 0
    with path.open("a", encoding="utf-8") as f:
        for lead in leads:
            f.write(json.dumps(lead.to_dict(), ensure_ascii=False) + "\n")
            count += 1
    return count

import json
from typing import Iterator

def read_leads_jsonl(path: Path) -> Iterator[Lead]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield Lead.from_dict(json.loads(line))
