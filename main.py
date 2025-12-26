from autoops.llm.client import OpenAIClient
from autoops.core.tool_router import ToolRegistry
from autoops.core.tool_pipeline import select_and_run_tool
from autoops.tools.text_tools import summarize_text_local


def main():
    client = OpenAIClient()

    # Register tools (allowlist)
    registry = ToolRegistry()
    registry.register("summarize_text_local", summarize_text_local)

    user_request = "Summarize this text in 2 sentences: Day 10 introduces tool calling so the model can request functions with structured inputs. We validate the request and execute a safe allowlisted tool. This enables agents."

    result = select_and_run_tool(client, registry, user_request)

    print("TOOL RESULT:")
    print(result)


if __name__ == "__main__":
    main()
