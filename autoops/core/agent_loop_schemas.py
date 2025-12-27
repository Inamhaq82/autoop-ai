from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AgentState(BaseModel):
    """
    Tracks what the agent has learned/produced so far.

    Reason:
    - The model must see context across iterations.
    Benefit:
    - Enables replanning based on tool results (not guesswork).
    """

    notes: List[str] = Field(default_factory=list)
    last_tool_results: List[Dict[str, Any]] = Field(default_factory=list)


class DoneCheck(BaseModel):
    """
    Model tells us whether we are done.

    Reason:
    - Prevents endless loops.
    Benefit:
    - Deterministic stop condition with structured output.
    """

    done: bool
    rationale: str


class AgentRunResult(BaseModel):
    """
    Final output of the iterative agent loop.

    Reason:
    - One typed object to save/log later.
    Benefit:
    - Easy to persist and compare across runs.
    """

    run_id: str
    ok: bool
    objective: str
    iterations: int
    state: AgentState
    final_answer: Optional[str] = None
