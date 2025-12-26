from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, Field


class ToolRequest(BaseModel):
    """
    Reason:
    - Single, strict format for model-to-system tool calls.
    Benefit:
    - Your router can validate tool calls deterministically.
    """
    tool_name: str = Field(description="Name of the tool to execute")
    args: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    request_id: Optional[str] = Field(default=None, description="Optional correlation id")


class ToolResult(BaseModel):
    """
    Reason:
    - Standardize tool outputs so downstream steps can rely on structure.
    Benefit:
    - Tools become composable building blocks.
    """
    tool_name: str
    ok: bool
    data: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


# Optional: a schema for a known tool output
class SummarizeTextOutput(BaseModel):
    summary: str
    key_points: list[str]
