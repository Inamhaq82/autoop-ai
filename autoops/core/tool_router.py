from typing import Callable, Dict, Any

from autoops.core.tool_schemas import ToolResult

ToolFn = Callable[..., Dict[str, Any]]


class ToolRegistry:
    """
    Reason:
    - Maintain an allowlist of tools.
    Benefit:
    - Prevents accidental/unsafe tool execution.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, ToolFn] = {}

    def register(self, name: str, fn: ToolFn) -> None:
        if name in self._tools:
            raise ValueError(f"Tool already registered: {name}")
        self._tools[name] = fn

    def has(self, name: str) -> bool:
        return name in self._tools

    def run(self, req) -> ToolResult:
        """
        Accepts any request object that has:
        - req.tool_name: str
        - req.args: dict
        (Works for ToolRequest and PlanStep.)
        """
        tool_name = req.tool_name
        args = req.args

        if tool_name not in self._tools:
            return ToolResult(tool_name=tool_name, ok=False, error="Unknown tool")

        fn = self._tools[tool_name]
        try:
            out = fn(**args)
            if not isinstance(out, dict):
                return ToolResult(
                    tool_name=tool_name, ok=False, error="Tool returned non-dict output"
                )
            return ToolResult(tool_name=tool_name, ok=True, data=out)
        except TypeError as e:
            return ToolResult(
                tool_name=tool_name, ok=False, error=f"Bad tool args: {e}"
            )
        except Exception as e:
            return ToolResult(
                tool_name=tool_name,
                ok=False,
                error=f"Tool error: {type(e).__name__}: {e}",
            )
