import uuid

def new_run_id() -> str:
    """
    Reason:
    - A single identifier to tie together all logs (prompt load, attempts, repair, parse/validate).
    Benefit:
    - Debugging becomes fast: you can grep one id and see the whole story.
    """
    return uuid.uuid4().hex
