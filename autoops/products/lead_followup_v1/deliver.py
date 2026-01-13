from __future__ import annotations

from autoops.products.lead_followup_v1.run import main as ingest_main
from autoops.products.lead_followup_v1.process import main as process_main

def main() -> int:
    ingest_main()
    process_main()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
