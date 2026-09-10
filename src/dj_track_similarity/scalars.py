"""Scalar coercion shared by writers, readers, jobs and the evaluation layer.

Every function here used to be copied into whichever module needed it. The
names carry the contract, because the contracts genuinely differ and reading
the call site should be enough to know which one applies:

``coerced_*``
    Accepts whatever ``int()`` or ``float()`` accepts.
``parsed_*``
    Renders the value as text and strips it first, so ``" 7 "`` is a valid
    seven. Used where a value arrives from a CSV cell or a CLI argument.
``*_or_none``
    Returns ``None`` instead of raising. Seventeen helpers across this
    repository already carry that suffix and every one of them is lenient, so
    the suffix is the reliable signal here; the more common ``optional_``
    prefix is not, because it sits on strict validators too.

Every numeric helper rejects ``bool``. Two call sites used to accept it, so a
JSON ``true`` in a score field became ``1.0``; that was a missing guard rather
than a decision, and it is gone.
"""

from __future__ import annotations

import math


def coerced_text(value: object, field_name: str) -> str:
    if value is None:
        raise ValueError(f"{field_name} must not be empty")
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


def positive_int(value: object, field_name: str) -> int:
    """Require an ``int`` that is already positive; never coerce."""

    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def coerced_positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive integer")
    try:
        clean_value = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be a positive integer") from error
    if clean_value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return clean_value


def parsed_positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive integer")
    try:
        clean_value = int(str(value).strip())
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be a positive integer") from error
    if clean_value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return clean_value


def non_negative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a non-negative integer")
    try:
        clean_value = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"{field_name} must be a non-negative integer"
        ) from error
    if clean_value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return clean_value


def positive_int_or_none(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def finite_number(value: object, field_name: str) -> float:
    """Coerce to a finite float, rejecting ``bool``."""

    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be a finite number") from error
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be a finite number")
    return number


def non_negative_finite_float(value: object, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a finite non-negative number")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"{field_name} must be a finite non-negative number"
        ) from error
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{field_name} must be a finite non-negative number")
    return number


def finite_float_or_none(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
