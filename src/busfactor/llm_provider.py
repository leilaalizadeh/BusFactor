"""LLM provider — the one function the whole team uses to call a model (Teammate 2).

complete_json(prompt, schema, fixture=None) -> dict

- Live mode (DEMO_MODE is not true AND LLM_API_KEY is set): calls Claude with a JSON
  schema as structured output, validates the JSON, retries once on bad JSON.
- Demo mode (DEMO_MODE=true, or no key): never touches the network. Returns the
  caller's deterministic `fixture` with "is_synthetic": True, or raises LLMUnavailable
  if the caller has no fixture. Fixture output is never presented as model inference.
"""
from __future__ import annotations

import copy
import json
import logging
import os
from typing import Optional

try:  # .env support is optional
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-5-5"
TIMEOUT_S = 60
# Models that accept server-side refusal fallbacks with the "default" routing form.
_FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1"}
_UNSUPPORTED_SCHEMA_KEYS = {"maxItems", "minItems", "maxLength", "minLength", "minimum", "maximum"}


class LLMUnavailable(RuntimeError):
    """No live model and no fixture for this call (or the model refused / failed)."""


def demo_mode() -> bool:
    return os.getenv("DEMO_MODE", "false").strip().lower() in {"1", "true", "yes"}


def llm_available() -> bool:
    return not demo_mode() and bool(os.getenv("LLM_API_KEY"))


def complete_json(prompt: str, schema: dict, fixture: Optional[dict] = None) -> dict:
    """Return a dict matching `schema`, with an added boolean "is_synthetic"."""
    if not llm_available():
        if fixture is None:
            raise LLMUnavailable("Demo mode (or no LLM_API_KEY) and no demo fixture for this call.")
        return {**copy.deepcopy(fixture), "is_synthetic": True}

    last_error: Exception | None = None
    for _attempt in range(2):  # 1 retry on bad JSON
        text = _call_claude(prompt, schema)
        try:
            data = json.loads(text)
            if not isinstance(data, dict):
                raise ValueError("model output is not a JSON object")
            missing = [k for k in schema.get("required", []) if k not in data]
            if missing:
                raise ValueError(f"missing fields {missing}")
            check_types(data, schema)
            data["is_synthetic"] = False
            return data
        except (json.JSONDecodeError, ValueError) as err:
            last_error = err
            log.warning("Bad JSON from model, retrying: %s", err)
    raise LLMUnavailable(f"Model returned invalid JSON twice: {last_error}")


_JSON_TYPES = {"string": str, "integer": int, "boolean": bool, "array": list, "object": dict, "number": (int, float)}


def check_types(data, schema: dict, path: str = "$") -> None:
    """Validate types and enums of model output against the schema (raises ValueError)."""
    expected = schema.get("type")
    py = _JSON_TYPES.get(expected)
    if py is not None:
        bad_bool = expected in ("integer", "number") and isinstance(data, bool)
        if not isinstance(data, py) or bad_bool:
            raise ValueError(f"{path} should be {expected}")
    if "enum" in schema and data not in schema["enum"]:
        raise ValueError(f"{path} must be one of {schema['enum']}")
    if expected == "object":
        for key, sub in schema.get("properties", {}).items():
            if key in data:
                check_types(data[key], sub, f"{path}.{key}")
    if expected == "array" and "items" in schema:
        for i, item in enumerate(data):
            check_types(item, schema["items"], f"{path}[{i}]")


def _strict(schema: dict) -> dict:
    """Make a schema valid for structured outputs: closed objects, no size constraints."""
    def walk(node):
        if isinstance(node, dict):
            node = {k: walk(v) for k, v in node.items() if k not in _UNSUPPORTED_SCHEMA_KEYS}
            if node.get("type") == "object":
                node["additionalProperties"] = False
            return node
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node
    return walk(copy.deepcopy(schema))


def _call_claude(prompt: str, schema: dict) -> str:
    import anthropic

    model = os.getenv("LLM_MODEL") or DEFAULT_MODEL
    client = anthropic.Anthropic(api_key=os.environ["LLM_API_KEY"], timeout=TIMEOUT_S, max_retries=2)
    kwargs: dict = dict(
        model=model,
        max_tokens=16000,
        output_config={"format": {"type": "json_schema", "schema": _strict(schema)}, "effort": "medium"},
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        if model in _FALLBACK_MODELS:
            # Server-side fallback: if a safety classifier declines, the API retries on another model.
            response = client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"], extra_body={"fallbacks": "default"}, **kwargs
            )
        else:
            response = client.messages.create(**kwargs)
    except anthropic.RateLimitError as err:
        raise LLMUnavailable("Model rate-limited; try again shortly.") from err
    except anthropic.APIStatusError as err:
        raise LLMUnavailable(f"Model API error {err.status_code}: {err.message}") from err
    except anthropic.APIConnectionError as err:
        raise LLMUnavailable("Cannot reach the model API (network).") from err

    if response.stop_reason == "refusal":
        raise LLMUnavailable("The model declined this request.")
    if response.stop_reason == "max_tokens":
        raise LLMUnavailable("Model output was cut off (max_tokens).")
    return next((b.text for b in response.content if b.type == "text"), "")
