"""What a person is told when a background job fails. The raw exception (SQL, parameters, vendor
responses) goes to the log only; the screen gets a short sentence that says what to do."""

from sqlalchemy.exc import IntegrityError

# Exceptions whose own message was written for people, so it is shown as it is.
_READABLE = (ValueError, LookupError)
_MAX_LEN = 200

GENERIC = "Something went wrong while running this. It has been logged; please try again."
DUPLICATE = (
    "This company already exists in your list under another record, so nothing was changed. "
    "Open it from the Companies page."
)
IN_USE = "This could not be saved because other records still depend on it. Nothing was changed."
BUSY = "The AI service is busy right now. Wait a minute and try again."
SLOW = "A data provider did not respond in time. Try again in a moment."


def _is_unique_violation(exc: IntegrityError) -> bool:
    detail = f"{type(exc.orig).__name__} {exc.orig}".lower()
    return "unique" in detail or "duplicate key" in detail


def friendly_error(exc: BaseException) -> str:
    text = str(exc)
    lowered = text.lower()
    if isinstance(exc, IntegrityError):
        return DUPLICATE if _is_unique_violation(exc) else IN_USE
    if any(token in lowered for token in ("429", "rate limit", "quota", "resource_exhausted")):
        return BUSY
    if any(token in type(exc).__name__.lower() for token in ("timeout", "connect")):
        return SLOW
    # Our own error types (and GeminiClientError / LLMError) carry readable messages. Anything
    # that looks like SQL or a stack of parameters never does.
    readable = isinstance(exc, _READABLE) or type(exc).__name__ in _READABLE_NAMES
    if readable and "[SQL" not in text and "\n" not in text:
        return text[:_MAX_LEN]
    return GENERIC


_READABLE_NAMES = {
    "GeminiClientError",
    "LLMError",
    "NoCriteriaConfiguredError",
    "CompanyNotFoundError",
    "DocumentReadError",
}
