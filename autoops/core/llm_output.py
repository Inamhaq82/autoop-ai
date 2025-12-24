import json
from typing import Type, TypeVar
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class LLMInvalidJSON(ValueError):
    """Raised when model output is not valid JSON."""


class LLMSchemaViolation(ValueError):
    """Raised when JSON is valid but does not match schema."""


def parse_and_validate(raw_output: str, schema: Type[T]) -> T:
    """
    Parse raw LLM output as JSON and validate against a Pydantic schema.

    Reason:
    - Centralizes parsing + validation
    - Produces consistent exception types for retry policy

    Benefit:
    - Any caller can trust returned objects
    - Retry logic becomes deterministic (based on exception types)
    """
    try:
        data = json.loads(raw_output)
    except json.JSONDecodeError as e:
        raise LLMInvalidJSON("LLM returned invalid JSON") from e

    try:
        return schema(**data)
    except ValidationError as e:
        raise LLMSchemaViolation("LLM JSON did not match schema") from e
