from __future__ import annotations

import httpx


class OpenAICompatibleClient:
    def __init__(self, base_url: str, api_key: str, *, timeout: float = 60.0, transport=None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.transport = transport
        self._client = httpx.Client(timeout=self.timeout, transport=self.transport, trust_env=False)

    def complete(self, prompt, *, model: str, temperature: float, max_tokens: int) -> str:
        payload = {"model": model, "messages": prompt if isinstance(prompt, list) else [{"role": "user", "content": prompt}], "temperature": temperature, "max_tokens": max_tokens}
        response = self._client.post(f"{self.base_url}/chat/completions", headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}, json=payload)
        response.raise_for_status()
        data = response.json()
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("OpenAI-compatible response did not contain choices[0].message.content") from exc

    def close(self) -> None:
        self._client.close()
