import json
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse, HTMLResponse

from app.api.dependencies import EvaluationDep, OptionalDriftDep, SettingsDep
from app.core.errors import NotFoundError, NotImplementedYetError
from app.evaluation.drift import drift_method
from app.evaluation.report_html import download_name, render_models_report
from app.schemas.models import ModelsResponse

REPORT_POLICY = (
    "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
    "img-src data:; base-uri 'none'; form-action 'none'"
)

router = APIRouter(tags=["models"])

FIGURES = {
    "best": "detector/{run}/best.png",
    "worst": "detector/{run}/worst.png",
    "false_alarms": "detector/{run}/false_alarms.png",
    "reliability": "detector/{run}/reliability.png",
    "plp": "detector/external/plp.png",
    "pairs": "satellite/pairs_{run}.png",
    "drift": "drift/blacksea.png",
}


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


@router.get("/models/figures/{name}", response_class=FileResponse)
def read_figure(name: str, settings: SettingsDep) -> FileResponse:
    template = FIGURES.get(name)
    if template is None:
        raise NotFoundError("Такого рисунка нет")
    manifest = settings.models_dir / "detector" / "service" / "detector.json"
    run = json.loads(manifest.read_text(encoding="utf-8"))["name"] if manifest.exists() else ""
    path = settings.reports_dir / "figures" / template.format(run=run)
    if not path.is_file():
        raise NotFoundError("Рисунок не построен")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "max-age=3600"})
