from pathlib import Path

def load_prompt(prompt_name: str, **kwargs) -> str:
    """
    Loads a prompt template from disk and fills in placeholders.

    Why this exists:
    - Keeps prompts out of code
    - Enables prompt versioning
    - Prevents hard-coded strings
    """

    prompt_path = Path(__file__).parent.parent / "prompts" / f"{prompt_name}.txt"

    with open(prompt_path, "r", encoding="utf-8") as f:
        template = f.read()

    return template.format(**kwargs)
