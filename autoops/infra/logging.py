import json
import time
from typing import Any, Dict

def log_event(event: str, **fields: Any) -> None:
    """
    Reason:
    - print() becomes chaos at scale; structured logs stay usable.
    Benefit:
    - You can filter by run_id, attempt, prompt_version, error_type, etc.
    """
    payload: Dict[str, Any] = {
        "ts": time.time(),
        "event": event,
        **fields,
    }
    print(json.dumps(payload, ensure_ascii=False))
