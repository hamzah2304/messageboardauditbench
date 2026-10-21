"""Is the model that answered the model that was asked for? Standard library only, so the
shell runner's post-processing can import it without the project environment."""

from __future__ import annotations

import re

# A dated snapshot of the same model: -1017, -202609, -20260929 or -2026-09-29.
_SNAPSHOT = re.compile(r"-(\d{4}|\d{6}|\d{8}|\d{4}-\d{2}-\d{2})")


def base(model_id: str) -> str:
    """'openrouter/openai/gpt-6.1-sol' -> 'gpt-6.1-sol'."""
    return str(model_id).rsplit("/", 1)[-1]


def same_model(asked: str, returned: str) -> bool:
    """True for the same id, or the same id plus a date snapshot suffix (never another version:
    'claude-opus-5-5' is not 'claude-opus-5')."""
    a, r = base(asked), base(returned)
    if not r or r == a:
        return True
    if r.startswith(a) and _SNAPSHOT.fullmatch(r[len(a):]):
        return True
    # The request may itself name a snapshot ('deepseek-v4.1-flash-1017') that the provider echoes bare.
    return a.startswith(r) and bool(_SNAPSHOT.fullmatch(a[len(r):]))
