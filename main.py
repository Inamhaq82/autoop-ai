from autoops.llm.client import OpenAIClient
from autoops.core.prompt_loader import load_prompt
from autoops.core.schemas import TaskSummary
from autoops.infra.ids import new_run_id


def main():
    # 1️⃣ Initialize the LLM client FIRST
    run_id = new_run_id()
    client = OpenAIClient()

    # 2️⃣ Load the schema-aware prompt
    prompt = load_prompt(
        "task_summary_structured",
        task="Explain schema-first design in AI systems",
        version="v2",
    )

    # 3️⃣ Generate structured output with retry + repair
    result = client.generate_structured(prompt, TaskSummary)

    # 4️⃣ Inspect result (temporary for CLI testing)
    print("STRUCTURED RESULT:")
    print(result)

    print("\nSUMMARY:")
    print(result.summary)

    print("\nKEY POINTS:")
    for p in result.key_points:
        print("-", p)


if __name__ == "__main__":
    main()
