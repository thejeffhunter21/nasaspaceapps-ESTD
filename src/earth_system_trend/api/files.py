"""J4: read results files from disk (always checked against the contract)."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from ..contract import ContractError, Results, load_results


def read_results(path: str | Path) -> Results:
    """Return the checked results, or raise ContractError (missing, bad JSON, wrong shape)."""
    return load_results(path)


def read_or_http_error(path: str | Path) -> Results:
    """Same, but as an HTTP answer: 404 if the file is missing, 500 if it is broken."""
    try:
        return read_results(path)
    except ContractError as exc:
        status = 404 if "file not found" in str(exc) else 500
        raise HTTPException(status_code=status, detail=str(exc)) from exc
