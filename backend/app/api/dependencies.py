from typing import Annotated

from fastapi import Depends, Request

from app.analysis.service import AnalysisService
from app.case.repository import CaseRepository
from app.core.config import Settings


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_repository(request: Request) -> CaseRepository:
    return request.app.state.repository


def get_analysis_service(request: Request) -> AnalysisService:
    return request.app.state.analysis


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
RepositoryDep = Annotated[CaseRepository, Depends(get_repository)]
AnalysisDep = Annotated[AnalysisService, Depends(get_analysis_service)]
