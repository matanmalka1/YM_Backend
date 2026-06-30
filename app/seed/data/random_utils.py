from __future__ import annotations

from random import Random

from app.utils.id_validation import validate_israeli_id_checksum

from .constants import FIRST_NAMES, LAST_NAMES


def full_name(rng: Random) -> str:
    return f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"


def _check_digit_for_base(base_digits: str) -> str:
    if len(base_digits) != 8 or not base_digits.isdigit():
        raise ValueError("base_digits must contain exactly 8 digits")
    for digit in "0123456789":
        candidate = base_digits + digit
        if validate_israeli_id_checksum(candidate):
            return digit
    raise RuntimeError(f"Failed to compute checksum digit for {base_digits}")


def generate_valid_israeli_id(
    serial: int,
    *,
    prefix: str = "",
    width: int | None = None,
) -> str:
    if not prefix.isdigit():
        raise ValueError("prefix must contain digits only")
    if len(prefix) > 8:
        raise ValueError("prefix may contain at most 8 digits")

    body_width = width if width is not None else 8 - len(prefix)
    if body_width < 0:
        raise ValueError("width is too small for the chosen prefix")

    body = str(serial).zfill(body_width)[-body_width:]
    base_digits = (prefix + body).zfill(8)
    return base_digits + _check_digit_for_base(base_digits)
