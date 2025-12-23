from autoops.llm.client import OpenAIClient
from autoops.core.prompt_loader import load_prompt
from autoops.core.schemas import TaskSummary
import json


def main():
    # 1️⃣ Initialize the LLM client (must exist BEFORE use)
    client = OpenAIClient()

    # 2️⃣ Load schema-aware prompt
    prompt = load_prompt(
        "task_summary_structured",
        task="Explain schema-first design in AI systems"
    )

    # 3️⃣ Call the LLM
    raw_output = client.generate(prompt)

    # 4️⃣ Parse + validate structured output
    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Model did not return valid JSON.\nRaw output:\n{raw_output}"
        ) from e

    result = TaskSummary(**parsed)

    # 5️⃣ Inspect result (temporary for Day 07)
    print("STRUCTURED RESULT:")
    print(result)

    print("\nSUMMARY:")
    print(result.summary)

    print("\nKEY POINTS:")
    for point in result.key_points:
        print("-", point)


if __name__ == "__main__":
    main()
