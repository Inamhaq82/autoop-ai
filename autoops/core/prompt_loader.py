from pathlib import Path

PROMPT_DIR = Path(__file__).parent.parent / "prompts"

def load_prompt(name: str, *, version: str = "v1", **kwargs) -> str:
    """
    Reason:
    - Prompts must be versioned and reproducible.
    Benefit:
    - You can A/B test prompts, roll back, and run evals across versions.
    """
    # supports both:
    # 1) autoops/prompts/name/v1.txt
    # 2) legacy autoops/prompts/name.txt  (fallback)
    versioned_path = PROMPT_DIR / name / f"{version}.txt"
    legacy_path = PROMPT_DIR / f"{name}.txt"

    prompt_path = versioned_path if versioned_path.exists() else legacy_path

    with open(prompt_path, "r", encoding="utf-8") as f:
        template = f.read()

    return template.format(**kwargs)
