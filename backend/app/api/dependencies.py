from typing import Annotated

from fastapi import Depends, Request

from app.analysis.service import AnalysisService
from app.case.repository import CaseRepository
from app.core.config import Settings
from app.core.errors import NotImplementedYetError
from app.drift.service import DriftService
from app.evaluation.reports import EvaluationReports
from app.survey.service import SurveyService


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_repository(request: Request) -> CaseRepository:
    return request.app.state.repository


def get_analysis_service(request: Request) -> AnalysisService:
    return request.app.state.analysis


def get_evaluation(request: Request) -> EvaluationReports:
    return request.app.state.evaluation


def find_drift_service(request: Request) -> DriftService | None:
    return getattr(request.app.state, "drift", None)


def get_drift_service(request: Request) -> DriftService:
    service = find_drift_service(request)
    if service is None:
        raise NotImplementedYetError("Модуль дрейфа не подключён")
    return service


def find_survey_service(request: Request) -> SurveyService | None:
    return getattr(request.app.state, "survey", None)


def get_survey_service(request: Request) -> SurveyService:
    service = find_survey_service(request)
    if service is None:
        raise NotImplementedYetError("Модуль планирования обследований не подключён")
    return service


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
RepositoryDep = Annotated[CaseRepository, Depends(get_repository)]
AnalysisDep = Annotated[AnalysisService, Depends(get_analysis_service)]
EvaluationDep = Annotated[EvaluationReports, Depends(get_evaluation)]
DriftDep = Annotated[DriftService, Depends(get_drift_service)]
OptionalDriftDep = Annotated[DriftService | None, Depends(find_drift_service)]
SurveyDep = Annotated[SurveyService, Depends(get_survey_service)]
OptionalSurveyDep = Annotated[SurveyService | None, Depends(find_survey_service)]
