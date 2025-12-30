from autoops.llm.client import OpenAIClient
from autoops.core.tool_router import ToolRegistry
from autoops.tools.text_tools import summarize_text_local
from autoops.core.agent_loop import run_agent_loop


def main():
    client = OpenAIClient()

    registry = ToolRegistry()
    registry.register("summarize_text_local", summarize_text_local)

    objective = (
        "Summarize this in 2 sentences and list key points: "
        "Day 12 adds an observe-replan loop so the agent can adapt based on tool outputs. "
        "It uses a done-check schema to stop deterministically."
    )

    result = run_agent_loop(
        client, registry, objective, max_iterations=3, planner_version="v2"
    )

    print(result)


if __name__ == "__main__":
    main()
