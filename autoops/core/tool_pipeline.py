from autoops.core.prompt_loader import load_prompt
from autoops.core.llm_output import parse_and_validate
from autoops.core.tool_schemas import ToolRequest, ToolResult
from autoops.core.tool_router import ToolRegistry


def select_and_run_tool(client, registry: ToolRegistry, user_request: str) -> ToolResult:
    """
    Reason:
    - One function to handle: selection -> validation -> execution.
    Benefit:
    - main.py stays thin; future API endpoints can call this directly.
    """
    prompt = load_prompt("tool_select", version="v1", user_request=user_request)

    # Ask model to produce ToolRequest JSON (validated)
    tool_req = client.generate_structured(prompt, ToolRequest)

    # Execute tool safely from allowlist
    return registry.run(tool_req)
