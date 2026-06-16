from __future__ import annotations

import os
from dataclasses import dataclass
import requests


class LLMError(RuntimeError):
    pass


@dataclass
class OpenRouterConfig:
    model: str
    temperature: float = 0.2
    site_url: str = "http://localhost"
    app_name: str = "bounty-pi-agent"


class OpenRouterClient:
    """Tiny OpenRouter client for glue tasks; Pi remains the preferred interactive harness."""

    endpoint = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, config: OpenRouterConfig):
        self.config = config
        self.api_key = os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise LLMError("OPENROUTER_API_KEY is not set")

    def chat(self, messages: list[dict[str, str]], *, max_tokens: int = 1200) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": os.environ.get("OPENROUTER_SITE_URL", self.config.site_url),
            "X-Title": os.environ.get("OPENROUTER_APP_NAME", self.config.app_name),
        }
        body = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": max_tokens,
        }
        resp = requests.post(self.endpoint, headers=headers, json=body, timeout=120)
        if resp.status_code >= 400:
            raise LLMError(f"OpenRouter error {resp.status_code}: {resp.text[:1000]}")
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected OpenRouter response: {data}") from exc
