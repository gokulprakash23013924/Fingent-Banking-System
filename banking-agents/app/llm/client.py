"""Provider-agnostic LLM adapter with native function calling and structured tool selection."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any


class LLMError(Exception):
    pass


class LLMUnavailable(LLMError):
    pass


@dataclass
class LLMResult:
    text: str
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: float
    fallback_used: bool = False


@dataclass
class LLMToolCallResult:
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    reply: str | None = None
    clarification: str | None = None
    is_greeting: bool = False
    out_of_scope: bool = False
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0.0
    model: str = "mock"


class BaseClient:
    name = "base"

    def available(self) -> bool:
        return True

    def complete(self, *, task: str, system: str, user: str, model: str,
                 max_tokens: int = 400, json_mode: bool = False) -> LLMResult:
        raise NotImplementedError

    def call_tools(self, *, system: str, user: str, tools: list[dict], model: str,
                   max_tokens: int = 800) -> LLMToolCallResult:
        raise NotImplementedError


class NoneClient(BaseClient):
    name = "none"

    def available(self) -> bool:
        return False

    def complete(self, **kw) -> LLMResult:
        raise LLMUnavailable("no LLM provider configured")

    def call_tools(self, **kw) -> LLMToolCallResult:
        raise LLMUnavailable("no LLM provider configured")


def _post_json(url: str, headers: dict, body: dict, timeout: float = 20.0) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={**headers, "content-type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise LLMError(f"HTTP {e.code} from provider: {e.read().decode()[:200]}") from e
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        raise LLMError(f"provider call failed: {e}") from e


class AnthropicClient(BaseClient):
    name = "anthropic"
    URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def available(self) -> bool:
        return bool(self.api_key)

    def complete(self, *, task, system, user, model, max_tokens=400, json_mode=False) -> LLMResult:
        if not self.api_key:
            raise LLMUnavailable("missing API key")
        t0 = time.perf_counter()
        data = _post_json(
            self.URL,
            {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
            {
                "model": model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user}]
            }
        )
        try:
            text = "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")
            usage = data.get("usage", {})
        except (KeyError, TypeError) as e:
            raise LLMError("unexpected response shape") from e
        return LLMResult(
            text, model, int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0)),
            (time.perf_counter() - t0) * 1000
        )

    def call_tools(self, *, system: str, user: str, tools: list[dict], model: str,
                   max_tokens: int = 800) -> LLMToolCallResult:
        if not self.api_key:
            raise LLMUnavailable("missing API key")
        t0 = time.perf_counter()
        anthropic_tools = [
            {
                "name": t["name"],
                "description": t["description"],
                "input_schema": t.get("parameters", {"type": "object", "properties": {}})
            } for t in tools
        ]
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "tools": anthropic_tools
        }
        data = _post_json(
            self.URL,
            {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
            body
        )
        content_blocks = data.get("content", [])
        text_reply = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text").strip()
        tool_calls = []
        for b in content_blocks:
            if b.get("type") == "tool_use":
                fn_name = b["name"]
                args = b.get("input", {})
                agent = next((t.get("agent", "banking") for t in tools if t["name"] == fn_name), "banking")
                tool_calls.append({"tool": fn_name, "agent": agent, "args": args})

        usage = data.get("usage", {})
        return LLMToolCallResult(
            tool_calls=tool_calls,
            reply=text_reply or None,
            tokens_in=int(usage.get("input_tokens", 0)),
            tokens_out=int(usage.get("output_tokens", 0)),
            latency_ms=(time.perf_counter() - t0) * 1000,
            model=model
        )


class OpenAICompatClient(BaseClient):
    name = "openai"

    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url

    def available(self) -> bool:
        return bool(self.api_key)

    def complete(self, *, task, system, user, model, max_tokens=400, json_mode=False) -> LLMResult:
        if not self.api_key:
            raise LLMUnavailable("missing API key")
        t0 = time.perf_counter()
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": 0,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        try:
            data = _post_json(f"{self.base_url}/chat/completions", {"authorization": f"Bearer {self.api_key}"}, body)
            text = data["choices"][0]["message"]["content"] or ""
            usage = data.get("usage", {})
            return LLMResult(
                text, model, int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0)),
                (time.perf_counter() - t0) * 1000
            )
        except Exception:
            from .mock import MockClient
            res = MockClient().complete(task=task, system=system, user=user, model="mock", max_tokens=max_tokens, json_mode=json_mode)
            res.fallback_used = True
            return res

    def call_tools(self, *, system: str, user: str, tools: list[dict], model: str,
                   max_tokens: int = 800) -> LLMToolCallResult:
        if not self.api_key:
            from .mock import MockClient
            return MockClient().call_tools(system=system, user=user, tools=tools, model="mock", max_tokens=max_tokens)
        t0 = time.perf_counter()
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t.get("parameters", {"type": "object", "properties": {}})
                }
            } for t in tools
        ]
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": 0,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "tools": openai_tools,
            "tool_choice": "auto"
        }
        try:
            data = _post_json(f"{self.base_url}/chat/completions", {"authorization": f"Bearer {self.api_key}"}, body)
            choice = data["choices"][0]
            msg = choice["message"]
            content = (msg.get("content") or "").strip()
            tool_calls = []
            if msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    fn_name = tc["function"]["name"]
                    try:
                        args = json.loads(tc["function"]["arguments"])
                    except Exception:
                        args = {}
                    agent = next((t.get("agent", "banking") for t in tools if t["name"] == fn_name), "banking")
                    tool_calls.append({"tool": fn_name, "agent": agent, "args": args})
            usage = data.get("usage", {})
            return LLMToolCallResult(
                tool_calls=tool_calls,
                reply=content or None,
                tokens_in=int(usage.get("prompt_tokens", 0)),
                tokens_out=int(usage.get("completion_tokens", 0)),
                latency_ms=(time.perf_counter() - t0) * 1000,
                model=model
            )
        except Exception:
            from .mock import MockClient
            return MockClient().call_tools(system=system, user=user, tools=tools, model="mock", max_tokens=max_tokens)


@lru_cache(maxsize=8)
def _build(provider: str, api_key: str, base_url: str) -> BaseClient:
    if provider == "mock":
        from .mock import MockClient
        return MockClient()
    if provider == "anthropic":
        return AnthropicClient(api_key)
    if provider == "openai":
        return OpenAICompatClient(api_key, base_url)
    return NoneClient()


def get_client(settings) -> BaseClient:
    return _build(settings.llm_provider, settings.llm_api_key, settings.llm_base_url)
