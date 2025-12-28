from pathlib import Path
from string import Template

PROMPT_DIR = Path(__file__).parent.parent / "prompts"


def load_prompt(name: str, *, version: str = "v1", **kwargs) -> str:
    """
    Reason:
    - Prompts must be versioned and reproducible.
    Benefit:
    - No brace escaping issues; safer schema-first prompts.
    """
    versioned_path = PROMPT_DIR / name / f"{version}.txt"
    legacy_path = PROMPT_DIR / f"{name}.txt"

    prompt_path = versioned_path if versioned_path.exists() else legacy_path

    with open(prompt_path, "r", encoding="utf-8") as f:
        template = Template(f.read())

    try:
        return template.substitute(**kwargs)
    except KeyError as e:
        raise RuntimeError(
            f"Prompt substitution failed for '{name}'. Missing variable: {e}"
        )


