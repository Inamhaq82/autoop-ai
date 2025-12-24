from autoops.llm.client import OpenAIClient
from autoops.core.prompt_loader import load_prompt
from autoops.core.schemas import TaskSummary


def main():
    # 1️⃣ Initialize the LLM client FIRST
    client = OpenAIClient()

    # 2️⃣ Load the schema-aware prompt
    prompt = load_prompt(
        "task_summary_structured", task="Explain schema-first design in AI systems"
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
