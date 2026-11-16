"""Small, bounded OpenAI Responses client for the report workflow."""

import math
import os

import requests


RATES = {
    "gpt-6-luna": (0.10, 0.50),
    "gpt-6.1-terra": (1.00, 5.00),
    "gpt-6.1-sol": (2.00, 10.00),
}


class ResponseBudget:
    def __init__(self):
        configured = os.getenv("OPENAI_RUN_COST_CAP_USD", "").strip()
        self.limit = float(configured) if configured else None
        if self.limit is not None and (not math.isfinite(self.limit) or self.limit < 0):
            raise ValueError("OPENAI_RUN_COST_CAP_USD must be a finite, non-negative amount")
        self.spent = 0.0

    def generate(
        self, model, system, prompt, *, output=2500, search=0,
        effort="low", json_object=True, timeout=120,
    ):
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is missing")
        input_rate, output_rate = RATES[model]
        body = {
            "model": model,
            "instructions": system,
            "input": prompt,
            "reasoning": {"effort": effort},
            "max_output_tokens": output,
            "store": False,
        }
        if json_object:
            body["text"] = {"format": {"type": "json_object"}}
        if search:
            body["tools"] = [{"type": "web_search", "search_context_size": "low"}]
            body["max_tool_calls"] = search

        # Bound the requested work before sending it. Retrieved search content
        # can vary, so report actual usage after every billable response.
        input_reserve = len((system + prompt).encode("utf-8")) + 4096 * search
        reserved = (input_reserve * input_rate + output * output_rate) / 1_000_000
        reserved += 0.01 * search
        if self.limit is not None and self.spent + reserved > self.limit:
            raise RuntimeError("Estimated OpenAI request would exceed this run's cost cap")
        self.spent += reserved
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {key}"},
            json=body,
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        items = data.get("output") or []
        usage = data.get("usage") or {}
        searches = sum(item.get("type") == "web_search_call" for item in items)
        if usage:
            cached = (usage.get("input_tokens_details") or {}).get("cached_tokens", 0)
            cache_multiplier = 0.1 if model == "gpt-6-luna" else 0.05
            uncached = usage.get("input_tokens", 0) - cached
            actual = (
                (uncached + cached * cache_multiplier) * input_rate
                + usage.get("output_tokens", 0) * output_rate
            ) / 1_000_000 + searches * 0.01
            self.spent += actual - reserved
        print(
            f"[OpenAI] model={model} input={usage.get('input_tokens', 0)} "
            f"output={usage.get('output_tokens', 0)} searches={searches} "
            f"estimated_run_cost=${self.spent:.4f}",
            flush=True,
        )
        if data.get("status") != "completed":
            reason = (data.get("incomplete_details") or {}).get("reason", data.get("status"))
            raise RuntimeError(f"OpenAI response did not complete: {reason}")
        text = "\n".join(
            part.get("text", "")
            for item in items if item.get("type") == "message"
            for part in item.get("content", []) if part.get("type") == "output_text"
        ).strip()
        if not text:
            raise RuntimeError("OpenAI returned no report text")
        return text, usage

