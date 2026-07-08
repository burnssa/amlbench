"""Thin Anthropic client wrapper.

Returns text + token usage + wall-clock latency so the observability arm can
record cost/latency without any special instrumentation of the agent itself.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Per-MTok USD pricing (input, output). Used for the observability "cost" metric.
# Approximate list prices; only relative magnitude matters for the PoC.
_PRICING = {
    "claude-fable-5": (10.0, 50.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    # OpenAI (approx list prices; only relative magnitude matters for the PoC).
    "gpt-5.5": (5.0, 15.0),          # frontier (standard tier; -pro is far pricier)
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
    "gpt-4.1": (2.0, 8.0),
    "gpt-4.1-mini": (0.4, 1.6),
    # Open-weight (via Groq) + xAI — approx; keyed by the full provider-prefixed id.
    "groq/gemma2-9b-it": (0.20, 0.20),
    "groq/llama-3.3-70b-versatile": (0.59, 0.79),
    "xai/grok-4.3": (3.0, 15.0),
}

# Models that reject the `temperature` parameter (it is removed on these; 400 if sent).
_NO_TEMPERATURE = {"claude-fable-5", "claude-opus-4-8"}


@dataclass
class LLMResponse:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_s: float = 0.0
    cost_usd: float = 0.0
    raw: dict = field(default_factory=dict)


class MissingAPIKey(RuntimeError):
    pass


# ── Provider routing ───────────────────────────────────────────────────────
# A model id is routed to a provider by prefix. Anthropic works today; the
# OpenAI + OpenAI-compatible hosts (Together / Fireworks / OpenRouter / Groq) are
# wired and become usable the moment their key is present — so going cross-provider
# is a config change, not a code change.
_OPENAI_COMPAT = {
    # provider: (base_url, key_env)
    "openai": (None, "OPENAI_API_KEY"),
    "together": ("https://api.together.xyz/v1", "TOGETHER_API_KEY"),
    "fireworks": ("https://api.fireworks.ai/inference/v1", "FIREWORKS_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "xai": ("https://api.x.ai/v1", "XAI_API_KEY"),   # Grok (OpenAI-compatible endpoint)
}


def _route(model: str) -> tuple[str, str]:
    """Return (provider, api_model_id)."""
    if model.startswith("claude"):
        return "anthropic", model
    if model.startswith("replicate/"):
        return "replicate", model.split("/", 1)[1]   # e.g. meta/meta-llama-3-70b-instruct
    if "/" in model and model.split("/", 1)[0] in _OPENAI_COMPAT:
        prov, mid = model.split("/", 1)
        return prov, mid
    if model.startswith(("gpt", "o1", "o3", "o4")):
        return "openai", model
    return "anthropic", model  # default


def _require_key(env: str) -> str:
    key = os.environ.get(env)
    if not key:
        raise MissingAPIKey(
            f"{env} is not set. Put it in a .env file at the repo root to use this "
            f"provider. (The offline data layer needs no keys.)"
        )
    return key


def _client():
    """Anthropic client (kept for back-compat / direct use)."""
    import anthropic

    return anthropic.Anthropic(api_key=_require_key("ANTHROPIC_API_KEY"))


def _cost(model: str, in_tok: int, out_tok: int) -> float:
    pin, pout = _PRICING.get(model, (3.0, 15.0))
    return (in_tok * pin + out_tok * pout) / 1_000_000


def _complete_anthropic(model, system, user, max_tokens, temperature) -> LLMResponse:
    kwargs = dict(model=model, system=system, max_tokens=max_tokens,
                  messages=[{"role": "user", "content": user}])
    # Some models (e.g. Opus 4.8) deprecate `temperature` and 400 if it is sent.
    if model not in _NO_TEMPERATURE:
        kwargs["temperature"] = temperature
    t0 = time.perf_counter()
    resp = _client().messages.create(**kwargs)
    latency = time.perf_counter() - t0
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    return LLMResponse(text=text, model=model, input_tokens=resp.usage.input_tokens,
                       output_tokens=resp.usage.output_tokens, latency_s=latency,
                       cost_usd=_cost(model, resp.usage.input_tokens, resp.usage.output_tokens))


def _complete_openai_compat(provider, api_model, full_model, system, user, max_tokens, temperature) -> LLMResponse:
    from openai import OpenAI

    base_url, key_env = _OPENAI_COMPAT[provider]
    client = OpenAI(api_key=_require_key(key_env), base_url=base_url)
    kwargs = dict(model=api_model,
                  messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    # OpenAI reasoning-tier models (gpt-5*, o1/o3/o4) require `max_completion_tokens`
    # and reject a non-default `temperature`. Other models use the classic params.
    if api_model.startswith(("gpt-5", "o1", "o3", "o4")):
        kwargs["max_completion_tokens"] = max_tokens
    else:
        kwargs["max_tokens"] = max_tokens
        kwargs["temperature"] = temperature
    t0 = time.perf_counter()
    resp = client.chat.completions.create(**kwargs)
    latency = time.perf_counter() - t0
    u = resp.usage
    in_tok, out_tok = u.prompt_tokens, u.completion_tokens
    return LLMResponse(text=resp.choices[0].message.content or "", model=full_model,
                       input_tokens=in_tok, output_tokens=out_tok, latency_s=latency,
                       cost_usd=_cost(full_model, in_tok, out_tok))


# Replicate throttles prediction creation hard on low-tier accounts (~6/min). We
# space call STARTS by a min interval (lock released before the API call so calls
# can still overlap in flight). Tune via REPLICATE_MIN_INTERVAL (seconds).
import threading

_REPLICATE_LOCK = threading.Lock()
_REPLICATE_LAST = [0.0]


def _replicate_throttle() -> None:
    interval = float(os.environ.get("REPLICATE_MIN_INTERVAL", "10.5"))
    with _REPLICATE_LOCK:
        wait = interval - (time.perf_counter() - _REPLICATE_LAST[0])
        if wait > 0:
            time.sleep(wait)
        _REPLICATE_LAST[0] = time.perf_counter()


# Per-model Replicate metadata, resolved once from the model's OpenAPI schema:
# the pinned version id, and the model's token-limit param name (varies:
# max_tokens / max_new_tokens / max_length). Official models (e.g. google-deepmind/*)
# 404 on the bare slug and must be run as "owner/model:version".
_REPLICATE_META: dict[str, tuple[str, str]] = {}


def _replicate_meta(client, api_model: str) -> tuple[str, str]:
    if api_model not in _REPLICATE_META:
        ver = client.models.get(api_model).latest_version
        props = ver.openapi_schema["components"]["schemas"]["Input"]["properties"]
        tok_key = next((k for k in ("max_tokens", "max_new_tokens", "max_length") if k in props),
                       "max_tokens")
        _REPLICATE_META[api_model] = (ver.id, tok_key)
    return _REPLICATE_META[api_model]


def _complete_replicate(api_model, full_model, system, user, max_tokens, temperature) -> LLMResponse:
    """Open-weight models via Replicate (own API; billed by time, not tokens — so
    token counts/cost are not tracked here, which is fine for the behavioral probe)."""
    import replicate

    token = os.environ.get("REPLICATE_API_TOKEN") or os.environ.get("REPLICATE_API_KEY")
    if not token:
        raise MissingAPIKey("REPLICATE_API_TOKEN is not set. Put it in a .env file at the repo root.")
    client = replicate.Client(api_token=token)
    version, tok_key = _replicate_meta(client, api_model)
    _replicate_throttle()
    t0 = time.perf_counter()
    out = client.run(f"{api_model}:{version}", input={
        "prompt": user,
        "system_prompt": system,
        tok_key: max_tokens,
        "temperature": max(temperature, 0.01),  # some Replicate models reject 0
    })
    latency = time.perf_counter() - t0
    text = "".join(out) if not isinstance(out, str) else out
    return LLMResponse(text=text, model=full_model, input_tokens=0, output_tokens=0,
                       latency_s=latency, cost_usd=0.0)


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=30))
def complete(
    *,
    model: str,
    system: str,
    user: str,
    max_tokens: int = 1400,
    temperature: float = 0.0,
) -> LLMResponse:
    """Single-turn completion, routed to the right provider by model id."""
    provider, api_model = _route(model)
    if provider == "anthropic":
        return _complete_anthropic(model, system, user, max_tokens, temperature)
    if provider == "replicate":
        return _complete_replicate(api_model, model, system, user, max_tokens, temperature)
    return _complete_openai_compat(provider, api_model, model, system, user, max_tokens, temperature)


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of a model response.

    Tolerant of ```json fences and leading/trailing prose.
    """
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fence.group(1) if fence else None
    if candidate is None:
        # Greedy match of the outermost braces.
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            candidate = text[start : end + 1]
    if candidate is None:
        raise ValueError(f"no JSON object found in response: {text[:200]!r}")
    return json.loads(candidate)


def api_key_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))
