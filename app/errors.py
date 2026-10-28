from collections.abc import Sequence
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

_LOCATIONS = {"body", "query", "path", "header", "cookie"}


def format_validation_errors(errors: Sequence[dict[str, Any]]) -> list[dict[str, str]]:
    formatted = []
    for error in errors:
        loc = [str(part) for part in error["loc"]]
        if len(loc) > 1 and loc[0] in _LOCATIONS:
            loc = loc[1:]
        formatted.append({"field": ".".join(loc), "message": error["msg"]})
    return formatted


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"detail": "Validation failed", "errors": format_validation_errors(exc.errors())},
    )
