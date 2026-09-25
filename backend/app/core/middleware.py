import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from app.core.errors import handle_unexpected_error
from app.core.request_context import REQUEST_ID_HEADER, resolve_request_id

logger = logging.getLogger("littora.http")


async def request_context_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request.state.request_id = resolve_request_id(request)
    started_at = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        response = await handle_unexpected_error(request, exc)
    elapsed_ms = (time.perf_counter() - started_at) * 1000
    response.headers[REQUEST_ID_HEADER] = request.state.request_id
    logger.debug(
        "%s %s -> %s in %.1fms",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response
