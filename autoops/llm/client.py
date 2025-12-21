import os
import time
from typing import Any

from openai import OpenAI


class LLMClient:
    def generate(self, prompt: str) -> str:
        raise NotImplementedError


class OpenAIClient(LLMClient):
    def __init__(self):
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

    def _call_openai(self, prompt: str) -> Any:
        """
        Single responsibility:
        - Make the OpenAI API call
        - Return the raw response
        """

        start = time.time()

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
        )

        latency = time.time() - start
        print(f"[LLM] latency={latency:.2f}s")

        return response

