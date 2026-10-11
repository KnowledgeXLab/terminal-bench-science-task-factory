"""Small OpenAI-compatible JSON client used by the task factory.

The client intentionally has no SDK dependency. ``API_KEY`` (or
``OPENAI_API_KEY``) and ``API_BASE`` (or ``OPENAI_BASE_URL``) are read only at
request time. They are never included in cache keys or written to disk.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def inference_parameters(temperature: float, max_tokens: int) -> dict[str, Any]:
    """Resolve optional wire parameters; retain legacy behavior when unset."""
    token_field = os.environ.get("TB_LLM_TOKEN_LIMIT_PARAMETER", "max_tokens")
    if token_field not in {"max_tokens", "max_completion_tokens"}:
        raise ValueError("TB_LLM_TOKEN_LIMIT_PARAMETER must be max_tokens or max_completion_tokens")
    result: dict[str, Any] = {token_field: max_tokens}
    configured_temperature = os.environ.get("TB_LLM_TEMPERATURE", "default").strip()
    if configured_temperature != "omit":
        value = temperature if configured_temperature == "default" else float(configured_temperature)
        if not math.isfinite(value) or not 0 <= value <= 2:
            raise ValueError("TB_LLM_TEMPERATURE must be default, omit or a number between 0 and 2")
        result["temperature"] = value
    effort = os.environ.get("TB_LLM_REASONING_EFFORT", "").strip()
    if effort:
        if effort not in {"none", "minimal", "low", "medium", "high", "xhigh", "max"}:
            raise ValueError("Invalid TB_LLM_REASONING_EFFORT")
        result["reasoning_effort"] = effort
    return result


def load_env_file(path: Path) -> list[str]:
    """Load simple KEY=VALUE entries without overriding ambient variables."""
    loaded: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded


def _endpoint(base: str) -> str:
    base = base.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions" if base.endswith("/v1") else base + "/v1/chat/completions"


def _json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    if text.startswith("```"):
        parts = text.split("```", 2)
        if len(parts) == 3:
            text = parts[1].lstrip()
            if text.startswith("json"):
                text = text[4:].lstrip()
    start = text.find("{")
    if start < 0:
        raise ValueError("LLM response does not contain a JSON object")
    depth = 0
    quoted = False
    escaped = False
    for idx in range(start, len(text)):
        char = text[idx]
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                value = json.loads(text[start : idx + 1])
                if isinstance(value, dict):
                    return value
                break
    raise ValueError("LLM response does not contain a JSON object")


class OpenAICompatibleJSONClient:
    def __init__(self, *, model: str, cache_dir: Path, timeout: int = 180,
                 max_retries: int = 3, use_env_proxy: bool = False) -> None:
        self.model = model
        self.cache_dir = cache_dir
        self.timeout = timeout
        self.max_retries = max_retries
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler() if use_env_proxy else urllib.request.ProxyHandler({})
        )
        self.calls = 0
        self.cache_hits = 0

    def chat_json(self, *, system: str, user: str, prompt_version: str,
                  temperature: float = 0.2, max_tokens: int = 32000,
                  refresh_cache: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
        parameters = inference_parameters(temperature, max_tokens)
        payload_key = {
            "model": self.model, "system": system, "user": user,
            **parameters,
            "prompt_version": prompt_version,
        }
        cache_key = hashlib.sha256(
            json.dumps(payload_key, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        cache_path = self.cache_dir / f"{cache_key}.json"
        if cache_path.is_file() and not refresh_cache:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(cached, dict) and isinstance(cached.get("response"), dict):
                self.cache_hits += 1
                return cached["response"], {"cache_key": cache_key, "cache_hit": True}

        api_key = os.environ.get("API_KEY") or os.environ.get("OPENAI_API_KEY")
        api_base = os.environ.get("API_BASE") or os.environ.get("OPENAI_BASE_URL")
        if not api_key or not api_base:
            raise RuntimeError("API_KEY/API_BASE (or OPENAI_API_KEY/OPENAI_BASE_URL) must be set")
        request = urllib.request.Request(
            _endpoint(api_base),
            data=json.dumps({
                "model": self.model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                **parameters,
                "response_format": {"type": "json_object"},
            }, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                with self._opener.open(request, timeout=self.timeout) as response:
                    body = json.load(response)
                content = body["choices"][0]["message"]["content"]
                parsed = _json_object(str(content))
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps({"model": self.model, "prompt_version": prompt_version,
                                                  "response": parsed}, ensure_ascii=False, indent=2) + "\n",
                                      encoding="utf-8")
                self.calls += 1
                return parsed, {"cache_key": cache_key, "cache_hit": False}
            except (OSError, KeyError, IndexError, TypeError, ValueError, urllib.error.HTTPError) as exc:
                last_error = exc
                if attempt + 1 < self.max_retries:
                    time.sleep(1.5 ** attempt + random.random() * 0.2)
        raise RuntimeError(f"LLM call failed after {self.max_retries} attempts: {last_error}")
