import os
import time
from typing import Any, Type, TypeVar

from pydantic import BaseModel
from openai import OpenAI

from autoops.infra.logging import log_event
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
        # Determinism / model config
        self.model = "gpt-4o-mini"
        self.temperature = 0.0
        self.top_p = 1.0
        self.max_output_tokens = 400

        # Reliability config
        self.max_attempts = 3
        self.base_backoff_seconds = 1.0
        self.repair_enabled = True

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")

        self.client = OpenAI(api_key=api_key)

        # Cost tracking (placeholder estimate)
        self.total_tokens = 0
        self.total_cost = 0.0
        self.estimated_cost_per_1k_tokens = 0.03  # placeholder estimate

    def generate(self, prompt: str) -> str:
        response = self._call_openai(prompt)

        usage = response.usage
        tokens_used = usage.total_tokens
        cost = (tokens_used / 1000) * self.estimated_cost_per_1k_tokens

        self.total_tokens += tokens_used
        self.total_cost += cost

        log_event(
            "llm_usage",
            tokens=tokens_used,
            cost=cost,
            total_tokens=self.total_tokens,
            total_cost=self.total_cost,
        )

        return response.choices[0].message.content

    def generate_structured(self, prompt: str, schema: Type[T]) -> T:
        last_error: Exception | None = None
        raw_output: str | None = None

        for attempt in range(1, self.max_attempts + 1):
            try:
                log_event(
                    "llm_attempt",
                    attempt=attempt,
                    max_attempts=self.max_attempts,
                    model=self.model,
                    temperature=self.temperature,
                )

                raw_output = self.generate(prompt)
                return parse_and_validate(raw_output, schema)

            except LLMInvalidJSON as e:
                last_error = e
                log_event("llm_invalid_json", error_type=type(e).__name__)

                if self.repair_enabled and raw_output:
                    repaired = self._repair_json(raw_output, "invalid_json")
                    try:
                        return parse_and_validate(repaired, schema)
                    except Exception as e2:
                        last_error = e2
                        log_event("llm_repair_failed", error_type=type(e2).__name__)

                self._backoff(attempt)

            except LLMSchemaViolation as e:
                last_error = e
                log_event("llm_validation_error", error_type=type(e).__name__)

                if self.repair_enabled and raw_output:
                    repaired = self._repair_json(raw_output, "schema_violation")
                    try:
                        return parse_and_validate(repaired, schema)
                    except Exception as e2:
                        last_error = e2
                        log_event("llm_repair_failed", error_type=type(e2).__name__)

                self._backoff(attempt)

            except Exception as e:
                last_error = e
                log_event("llm_transient_error", error_type=type(e).__name__)
                self._backoff(attempt)

        raise RuntimeError(
            f"LLM failed after {self.max_attempts} attempts"
        ) from last_error

    def _call_openai(self, prompt: str) -> Any:
        start = time.time()

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.temperature,
            top_p=self.top_p,
            max_tokens=self.max_output_tokens,
        )

        latency = time.time() - start
        log_event("llm_latency", seconds=latency)

        return response

    def _backoff(self, attempt: int) -> None:
        delay = self.base_backoff_seconds * (2 ** (attempt - 1))
        log_event("llm_backoff", seconds=delay)
        time.sleep(delay)

    def _repair_json(self, raw_output: str, reason: str) -> str:
        schema_hint = (
            "summary: string; key_points: string[]; confidence: number between 0 and 1"
        )
        repair_prompt = load_prompt("json_repair", schema=schema_hint, raw=raw_output)

        log_event("llm_repair_attempt", reason=reason)
        return self.generate(repair_prompt)
