from autoops.llm.client import OpenAIClient
from autoops.core.tool_router import ToolRegistry
from autoops.tools.text_tools import summarize_text_local

from autoops.core.planner import create_plan
from autoops.core.agent_executor import execute_plan


def main():
    client = OpenAIClient()

    registry = ToolRegistry()
    registry.register("summarize_text_local", summarize_text_local)

    objective = (
        "Summarize the following text in 2 sentences and list key points: "
        "Day 11 adds multi-step planning where the model generates a plan of tool calls. "
        "The executor validates and runs each step safely. "
        "This is the base of an agent loop."
    )

    plan = create_plan(client, objective, version="v1")
    print("PLAN:")
    print(plan)

    summary = execute_plan(registry, plan)
    print("\nRUN SUMMARY:")
    print(summary)


if __name__ == "__main__":
    main()
