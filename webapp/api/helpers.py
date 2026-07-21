"""api/helpers.py — Shared utilities for API blueprints."""

# Single canonical definition; all blueprints import from here.
MAX_URL_LENGTH = 2048


def safe_int(value, default: int, min_val: int | None = None, max_val: int | None = None) -> int:
    """Parse an integer from a request parameter, returning default on failure."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        v = default
    if min_val is not None:
        v = max(v, min_val)
    if max_val is not None:
        v = min(v, max_val)
    return v
