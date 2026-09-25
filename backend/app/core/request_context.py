import re
import uuid

from fastapi import Request

REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,128}$")


def resolve_request_id(request: Request) -> str:
    incoming = request.headers.get(REQUEST_ID_HEADER, "")
    if _REQUEST_ID_PATTERN.fullmatch(incoming):
        return incoming
    return uuid.uuid4().hex


def get_request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)
