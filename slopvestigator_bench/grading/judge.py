"""Judge plumbing shared by every eval's grader.

Each grader builds its own messages, response format and arithmetic; this module owns what
they have in common: the provider route (OpenRouter may not fall back to another provider or
drop a parameter), the effort field each provider reads, and the check that the requested
model is the one that answered. A grader turns a `JudgeError` into an unscored result, never
a zero.
"""

from __future__ import annotations

from typing import Any

from inspect_ai.model import GenerateConfig, Model, ModelOutput

# No fallback provider, and fail rather than silently drop the effort or the response format.
OPENROUTER_ROUTE = {"provider": {"allow_fallbacks": False, "require_parameters": True}}


class JudgeError(RuntimeError):
    """The judge's answer cannot be used (wrong model, truncated)."""


def is_openrouter(model: Model | str) -> bool:
    return str(model).startswith("openrouter/")


def is_anthropic(model: Model | str) -> bool:
    name = str(model).removeprefix("openrouter/")
    return name.startswith("anthropic/") or name.startswith("claude")


def base_name(model: Model | str) -> str:
    """'openrouter/openai/gpt-6.1-sol' -> 'gpt-6.1-sol'."""
    return str(model).rsplit("/", 1)[-1]


def pin_route(config: GenerateConfig, model: Model | str) -> GenerateConfig:
    """Merge the OpenRouter route into the config's extra_body, keeping what is already there."""
    if not is_openrouter(model):
        return config
    return config.merge(GenerateConfig(extra_body={**(config.extra_body or {}), **OPENROUTER_ROUTE}))


def served_mismatch(model: Model | str, out: ModelOutput) -> str | None:
    """A reason when the answer came from another model (a dated snapshot of it is fine)."""
    asked, returned = base_name(model), base_name(out.model or "")
    if returned and returned != asked and not returned.startswith(asked + "-"):
        return f"returned model {out.model} differs from {model}"
    return None


async def generate(model: Model, messages: list[Any], config: GenerateConfig) -> ModelOutput:
    """One judge call with the route pinned and the served model checked."""
    out = await model.generate(messages, config=pin_route(config, model))
    if reason := served_mismatch(model, out):
        raise JudgeError(reason)
    return out
