from autoops.core.prompt_loader import load_prompt
from autoops.core.agent_schemas import Plan


def create_plan(client, objective: str, version: str = "v1") -> Plan:
    """
    Reason:
    - Converts natural language objective into a validated Plan.
    Benefit:
    - Separates planning from execution (clean architecture).
    """
    prompt = load_prompt("planner", version=version, objective=objective)
    return client.generate_structured(prompt, Plan)
