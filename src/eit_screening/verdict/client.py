"""Client minimal du protocole compatible OpenAI (``/chat/completions``).

Le même code parle à Ollama ou vLLM en local et à un fournisseur hébergé :
seuls l'adresse, le modèle et la clé changent. La sortie est contrainte par un
schéma JSON (``response_format``) puis vérifiée par Pydantic ; une réponse non
conforme déclenche une nouvelle tentative.
"""

from __future__ import annotations

import json
import os
import time

import httpx
from pydantic import BaseModel, ValidationError

from .models import LlmRule


class ChatResult(BaseModel):
    content: dict | None
    raw: list[str]
    attempts: int
    seconds: float
    errors: list[str]


class ChatClient:
    def __init__(self, rule: LlmRule, transport: httpx.BaseTransport | None = None) -> None:
        self.rule = rule
        headers = {"Content-Type": "application/json"}
        key = os.environ.get(rule.api_key_env, "") if rule.api_key_env else ""
        if key:
            headers["Authorization"] = f"Bearer {key}"
        self._http = httpx.Client(
            base_url=rule.base_url.rstrip("/"), headers=headers, timeout=rule.timeout_seconds, transport=transport
        )

    def complete_json(self, messages: list[dict], schema: dict, validator: type[BaseModel]) -> ChatResult:
        """Demande une réponse JSON conforme à ``schema`` ; ``validator`` la contrôle."""
        body = {
            "model": self.rule.model,
            "messages": messages,
            "temperature": self.rule.temperature,
            "max_tokens": self.rule.max_tokens,
            "response_format": {"type": "json_schema", "json_schema": {"name": "verdict", "strict": True, "schema": schema}},
        }
        raw: list[str] = []
        errors: list[str] = []
        started = time.perf_counter()
        for attempt in range(1, self.rule.max_attempts + 1):
            try:
                response = self._http.post("/chat/completions", json=body)
                response.raise_for_status()
                text = response.json()["choices"][0]["message"]["content"] or ""
                raw.append(text)
                content = json.loads(text)
                validator.model_validate(content)
                return ChatResult(content=content, raw=raw, attempts=attempt,
                                  seconds=round(time.perf_counter() - started, 2), errors=errors)
            except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError, ValidationError) as error:
                errors.append(f"tentative {attempt} : {type(error).__name__} : {str(error)[:300]}")
        return ChatResult(content=None, raw=raw, attempts=self.rule.max_attempts,
                          seconds=round(time.perf_counter() - started, 2), errors=errors)
