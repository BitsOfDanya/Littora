from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.core.capabilities import CapabilityKey, CapabilityStatus


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    environment: str
    timestamp: datetime


class CapabilityState(BaseModel):
    key: CapabilityKey
    status: CapabilityStatus


class MetaResponse(BaseModel):
    service: str
    version: str
    api_version: str
    environment: str
    capabilities: list[CapabilityState]
