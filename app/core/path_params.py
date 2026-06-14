"""Shared path parameter annotations."""

from typing import Annotated

from fastapi import Path

PathId = Annotated[int, Path(ge=1)]
PositiveIntPath = Annotated[int, Path(ge=1)]
SigningTokenPath = Annotated[str, Path(min_length=32, max_length=256)]

__all__ = ["PathId", "PositiveIntPath", "SigningTokenPath"]
