"""J10: checks on user input, run before any handler code."""

from typing import Annotated

from fastapi import Query

# Letters, digits, spaces and simple punctuation; 1 to 100 characters.
REGION_PATTERN = r"^[\w .,()'/-]{1,100}$"

RegionParam = Annotated[
    str | None,
    Query(min_length=1, max_length=100, pattern=REGION_PATTERN,
          description="Region id or label, e.g. phoenix_northwest"),
]
