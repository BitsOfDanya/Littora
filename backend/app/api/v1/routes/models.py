from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from app.api.dependencies import EvaluationDep, OptionalDriftDep, SettingsDep
from app.core.errors import NotImplementedYetError
from app.evaluation.drift import drift_method
from app.evaluation.report_html import download_name, render_models_report
from app.schemas.models import ModelsResponse

REPORT_POLICY = (
    "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
    "img-src data:; base-uri 'none'; form-action 'none'"
)

router = APIRouter(tags=["models"])


@router.get("/models", response_model=ModelsResponse)
def read_models(
    evaluation: EvaluationDep, drift: OptionalDriftDep, settings: SettingsDep
) -> ModelsResponse:
    detector, concentration, sources = evaluation.load()
    if detector is None and concentration is None:
        raise NotImplementedYetError("Артефакты оценки моделей не найдены")
    return ModelsResponse(
        detector=detector,
        concentration=concentration,
        drift=drift_method(drift, settings.reports_dir) if drift is not None else None,
        sources=sources,
    )


@router.get("/models/report.html", response_class=HTMLResponse)
def read_models_report(
    evaluation: EvaluationDep,
    drift: OptionalDriftDep,
    settings: SettingsDep,
    auto_print: Annotated[bool, Query(alias="print")] = False,
    download: bool = False,
) -> HTMLResponse:
    response = read_models(evaluation, drift, settings)
    generated_at = datetime.now(UTC)
    body = render_models_report(
        response,
        reports_dir=settings.reports_dir,
        models_dir=settings.models_dir,
        version=settings.version,
        generated_at=generated_at,
        auto_print=auto_print and not download,
        standalone=download,
    )
    headers = {"Cache-Control": "no-store", "Content-Security-Policy": REPORT_POLICY}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{download_name(generated_at)}"'
    return HTMLResponse(body, headers=headers)
