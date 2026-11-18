"""Thin wrapper around the Claude API: structured JSON output, server tools, pause_turn, refusals."""
from __future__ import annotations

import json
import logging
import threading
from typing import TypeVar

import anthropic
from pydantic import BaseModel

from . import config

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

_client: anthropic.Anthropic | None = None
MAX_CONTINUATIONS = 5

# USD per million tokens: (input, output, cache read). Cache writes are billed at 1.25x input.
# Update if prices change; unknown models are costed at Opus 5.5 rates.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 0.10),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
    "claude-fable-5-2": (8.00, 40.00, 0.20),
    "claude-opus-5": (5.00, 25.00, 0.50),
    "claude-opus-4-8": (5.00, 25.00, 0.50),
    "claude-sonnet-5": (2.00, 10.00, 0.20),
}
WEB_SEARCH_USD = 10.00 / 1000

_spent = 0.0
_spent_lock = threading.Lock()


def response_cost(resp) -> float:
    u = getattr(resp, "usage", None)
    if u is None:
        return 0.0
    inp, out, cread = PRICES.get(getattr(resp, "model", ""), PRICES["claude-opus-5-5"])
    usd = ((u.input_tokens or 0) * inp + (u.output_tokens or 0) * out
           + (getattr(u, "cache_read_input_tokens", 0) or 0) * cread
           + (getattr(u, "cache_creation_input_tokens", 0) or 0) * inp * 1.25) / 1e6
    stu = getattr(u, "server_tool_use", None)
    if stu is not None:
        usd += (getattr(stu, "web_search_requests", 0) or 0) * WEB_SEARCH_USD
    return usd


def _add_cost(usd: float) -> None:
    global _spent
    with _spent_lock:
        _spent += usd


def spent() -> float:
    """Estimated Claude spend (USD) in this process so far."""
    return _spent


class ClaudeRefusal(RuntimeError):
    pass


class OutOfCredits(RuntimeError):
    """The Anthropic account has no credit left; every further call would fail too."""


def is_out_of_credits(exc: Exception) -> bool:
    return "credit balance is too low" in str(exc).lower()


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(max_retries=4, timeout=900)
    return _client


def json_schema(model: type[BaseModel]) -> dict:
    """Pydantic schema with $refs inlined and keys the structured-output API doesn't need removed."""
    raw = model.model_json_schema()
    defs = raw.pop("$defs", {})

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(defs[node["$ref"].split("/")[-1]])
            out = {k: walk(v) for k, v in node.items() if k not in ("title", "default")}
            if out.get("type") == "object":
                out["additionalProperties"] = False
                out["required"] = list(out.get("properties", {}).keys())
            return out
        if isinstance(node, list):
            return [walk(n) for n in node]
        return node

    return walk(raw)


def structured_call(
    *,
    system: str,
    user: str,
    output: type[T],
    effort: str,
    tools: list[dict] | None = None,
    max_tokens: int = 32000,
) -> tuple[T, anthropic.types.beta.BetaMessage]:
    """One request (plus pause_turn continuations) whose final answer is validated against `output`."""
    messages: list[dict] = [{"role": "user", "content": user}]
    params = dict(
        model=config.MODEL,
        max_tokens=max_tokens,
        system=system,
        thinking={"type": "adaptive"},
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": json_schema(output)}},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if tools:
        params["tools"] = tools

    assistant_blocks: list = []
    for _ in range(MAX_CONTINUATIONS + 1):
        with client().beta.messages.stream(messages=messages, **params) as stream:
            resp = stream.get_final_message()
        _add_cost(response_cost(resp))
        assistant_blocks.extend(resp.content)
        if resp.stop_reason == "pause_turn":
            # Server-side tool loop hit its iteration limit: resend the turn so far and it resumes.
            messages = [messages[0], {"role": "assistant", "content": list(assistant_blocks)}]
            continue
        resp.content = assistant_blocks  # so callers see every search result from all continuations
        break
    else:
        raise RuntimeError("Too many pause_turn continuations")

    if resp.stop_reason == "refusal":
        cat = getattr(resp.stop_details, "category", None) if resp.stop_details else None
        raise ClaudeRefusal(f"Model declined (category={cat})")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("Response hit max_tokens before finishing")

    texts = [b.text for b in resp.content if b.type == "text" and b.text.strip()]
    if not texts:
        raise RuntimeError(f"No text output (stop_reason={resp.stop_reason})")
    return output.model_validate(json.loads(texts[-1])), resp


def web_search_failures(resp) -> int:
    """Server-tool errors arrive as 200s with an error object instead of a result list."""
    n = 0
    for b in resp.content:
        if b.type in ("web_search_tool_result", "web_fetch_tool_result"):
            content = getattr(b, "content", None)
            if getattr(content, "type", "").endswith("_error"):
                n += 1
                log.warning("%s error: %s", b.type, getattr(content, "error_code", "?"))
    return n


def seen_urls(resp) -> set[str]:
    """URLs that actually appeared in search/fetch results (used to drop invented citations)."""
    urls: set[str] = set()
    for b in resp.content:
        if b.type == "web_search_tool_result" and isinstance(b.content, list):
            urls.update(r.url for r in b.content if getattr(r, "url", None))
        elif b.type == "web_fetch_tool_result":
            url = getattr(b.content, "url", None)
            if url:
                urls.add(url)
    return urls
