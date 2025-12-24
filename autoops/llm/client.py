import os
import time
from typing import Any
from typing import Type, TypeVar
from pydantic import BaseModel
from openai import OpenAI

from autoops.core.prompt_loader import load_prompt
from autoops.core.llm_output import (
    parse_and_validate,
    LLMInvalidJSON,
    LLMSchemaViolation,
)

T = TypeVar("T", bound=BaseModel)


class LLMClient:
    def generate(self, prompt: str) -> str:
        raise NotImplementedError


class OpenAIClient(LLMClient):
    def __init__(self):

        self.max_attempts = 3
        self.base_backoff_seconds = 1.0
        self.repair_enabled = True

        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is not set")

        # Cost tracking
        self.total_tokens = 0
        self.total_cost = 0.0

        # Model config (explicit, not hidden)
        self.model = "gpt-4o-mini"
        self.cost_per_1k_tokens = 0.00015  # example, update as pricing changes

    def generate(self, prompt: str) -> str:
        response = self._call_openai(prompt)

        usage = response.usage
        tokens_used = usage.total_tokens

        cost = (tokens_used / 1000) * self.cost_per_1k_tokens

        self.total_tokens += tokens_used
        self.total_cost += cost

        print(
            f"[LLM] tokens={tokens_used} | cost=${cost:.6f} | total=${self.total_cost:.6f}"
        )

        return response.choices[0].message.content

    def generate_structured(self, prompt: str, schema: Type[T]) -> T:
        """
        Generate a response and return a validated schema object.

        Retry strategy:
        1) Try normal generation -> parse/validate
        2) On invalid JSON or schema violation:
           - attempt a single repair pass (optional)
           - retry generation
        3) On transient API failures:
           - backoff and retry
        """

        last_error: Exception | None = None
        raw_output: str | None = None

        for attempt in range(1, self.max_attempts + 1):
            try:
                print(f"[LLM] attempt={attempt}/{self.max_attempts}")

                raw_output = self.generate(prompt)  # uses your existing cost tracking
                return parse_and_validate(raw_output, schema)

            except (LLMInvalidJSON, LLMSchemaViolation) as e:
                last_error = e
                print(f"[LLM] validation_error={type(e).__name__}")

                if self.repair_enabled and raw_output:
                    repaired = self._repair_json(raw_output, schema)
                    try:
                        return parse_and_validate(repaired, schema)
                    except Exception as e2:
                        last_error = e2
                        print(f"[LLM] repair_failed={type(e2).__name__}")

                # backoff before retry
                self._backoff(attempt)

            except Exception as e:
                # Covers transient OpenAI/network issues
                last_error = e
                print(f"[LLM] transient_error={type(e).__name__}")
                self._backoff(attempt)

        # Exhausted attempts
        raise RuntimeError(
            f"LLM failed after {self.max_attempts} attempts"
        ) from last_error

    def _call_openai(self, prompt: str) -> Any:
        """
        Single responsibility:
        - Make the OpenAI API call
        - Return the raw response
        """

        start = time.time()

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )

        latency = time.time() - start
        print(f"[LLM] latency={latency:.2f}s")

        return response

    def _backoff(self, attempt: int) -> None:
        """
        Exponential backoff to reduce pressure on the API and avoid rate limits.
        """
        delay = self.base_backoff_seconds * (2 ** (attempt - 1))
        print(f"[LLM] backoff_seconds={delay:.2f}")
        time.sleep(delay)

    def _repair_json(self, raw_output: str, schema: Type[T]) -> str:
        """
        Ask the model to fix the JSON formatting/schema.
        """
        # Provide a schema hint WITHOUT braces to avoid .format brace collisions
        schema_hint = (
            "summary: string; key_points: string[]; confidence: number between 0 and 1"
        )

        repair_prompt = load_prompt("json_repair", schema=schema_hint, raw=raw_output)

        print("[LLM] running_json_repair_pass=true")
        repaired = self.generate(repair_prompt)

        return repaired
