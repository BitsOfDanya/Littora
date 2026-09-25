import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.request_context import REQUEST_ID_HEADER, get_request_id
from app.schemas.errors import ErrorBody, ErrorResponse

logger = logging.getLogger("littora.errors")


class AppError(Exception):
    status_code: int = HTTPStatus.BAD_REQUEST
    code: str = "bad_request"

    def __init__(self, message: str, *, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(AppError):
    status_code = HTTPStatus.NOT_FOUND
    code = "not_found"


class NotImplementedYetError(AppError):
    status_code = HTTPStatus.NOT_IMPLEMENTED
    code = "not_implemented"


def _status_code_slug(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase.lower().replace(" ", "_").replace("-", "_")
    except ValueError:
        return "http_error"


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = get_request_id(request)
    payload = ErrorResponse(
        error=ErrorBody(
            code=code,
            message=message,
            details=jsonable_encoder(details),
            request_id=request_id,
        )
    )
    response_headers = dict(headers or {})
    if request_id:
        response_headers[REQUEST_ID_HEADER] = request_id
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json"),
        headers=response_headers,
    )


async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    return _error_response(
        request,
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details,
    )


async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else HTTPStatus(exc.status_code).phrase
    details = None if isinstance(exc.detail, str) else exc.detail
    return _error_response(
        request,
        status_code=exc.status_code,
        code=_status_code_slug(exc.status_code),
        message=message,
        details=details,
        headers=exc.headers,
    )


async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return _error_response(
        request,
        status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        code="validation_error",
        message="Request validation failed",
        details=exc.errors(),
    )


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    return _error_response(
        request,
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        code="internal_error",
        message="Internal server error",
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
