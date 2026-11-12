"""LLM failures as exceptions, with whether a retry can help."""

import re

# Signs of a transient failure (overload, rate limit, network). Status codes
# must stand alone: "429" inside a request id or a token count is not one.
_RETRYABLE = re.compile(
    r"\b(?:429|500|502|503|504)\b"
    r"|unavailable|overloaded|rate.?limit|quota|capacity|too many requests"
    r"|resourceexhausted|servererror|deadline.?exceeded|timed? ?out"
    r"|connection (?:error|reset|refused|aborted)|temporarily",
    re.IGNORECASE,
)

# Prefixes engines use when they report a failure as text (legacy style).
_ERROR_PREFIXES = ("Error", "CLI Error")


class LLMError(RuntimeError):
    """A model call failed. ``retryable`` says whether trying again can help."""

    def __init__(self, message: str, *, retryable: bool | None = None):
        super().__init__(message)
        self.retryable = is_transient(message) if retryable is None else retryable


def is_transient(message: str) -> bool:
    return bool(_RETRYABLE.search(message))


def is_error_text(result: object) -> bool:
    """Whether an engine's return value is a failure reported as text."""
    return isinstance(result, str) and result.startswith(_ERROR_PREFIXES)
