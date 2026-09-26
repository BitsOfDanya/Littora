from __future__ import annotations

from typing import Any

import joblib
import numpy as np

from littora_ml.common.io import read_json, write_json
from littora_ml.common.paths import MODELS, REPORTS
from littora_ml.concentration.run import load_features
from littora_ml.concentration.validation import confidence_label

SERVICE_KINDS = ("idw", "tweedie", "median")


def _tweedie(model) -> dict[str, Any]:
    scaler, regressor = model.fitted.steps[0][1], model.fitted.steps[-1][1]
    return {
        "mean": scaler.mean_.tolist(),
        "scale": scaler.scale_.tolist(),
        "coef": regressor.coef_.tolist(),
        "intercept": float(regressor.intercept_),
    }


def _interval(values: list[float], digits: int = 0) -> str:
    return f"[{values[0]:+.{digits}f}; {values[1]:+.{digits}f}]"


def _band(values: dict[str, float], digits: int = 0) -> str:
    return f"{values['mean']:.{digits}f} ± {values['sd']:.{digits}f}"


def service_reason(profile: str, service: dict[str, Any], constant: float | None) -> str:
    baseline, candidates = service["baseline"], service["candidates"]
    digits = 1 if baseline["mae"]["mean"] < 100 else 0
    scope = (
        f"{confidence_label(service['confidence'])} ДИ, поправка Бонферрони на число кандидатов "
        f"({len(candidates)}), {service['repetitions']} повторов CV по дням съёмки"
    )
    deployed = service["deployed_model"]
    if deployed != "median":
        own = candidates[deployed]
        difference = own["difference_vs_median"]["mae"]
        return (
            f"полевая модель профиля {profile} ({deployed}, только координаты): "
            f"MAE {_band(own['mae'], digits)} против {_band(baseline['mae'], digits)} у медианы, "
            f"разница {difference['mean']:+.{digits}f} {_interval(difference['ci'], digits)} "
            f"({scope})"
        )
    rivals = ", ".join(
        f"{label} {row['difference_vs_median']['mae']['mean']:+.{digits}f} "
        f"{_interval(row['difference_vs_median']['mae']['ci'], digits)}"
        for label, row in candidates.items()
    )
    return (
        f"профиль {profile}: значимого выигрыша над медианой нет — у всех координатных "
        f"моделей верхняя граница ДИ разницы MAE ≥ 0, разница MAE: {rivals} ({scope}); "
        f"выдана медиана полевых данных {constant:.{digits}f} шт./км² с интервалом, "
        f"MAE медианы {_band(baseline['mae'], digits)}"
    )


def _candidate_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "mae": row["mae"]["mean"],
        "mae_sd": row["mae"]["sd"],
        "rmse": row["rmse"]["mean"],
        "rmse_sd": row["rmse"]["sd"],
        "coverage": row["coverage"]["mean"],
        "difference_mae": row["difference_vs_median"]["mae"],
        "difference_rmse": row["difference_vs_median"]["rmse"],
        "passes": row["passes"],
    }


def export_profile(report: str, profile: str, features) -> dict:
    folder = MODELS / "concentration" / report / profile
    meta = read_json(folder / "meta.json")
    model = joblib.load(folder / "service.joblib")
    if model.kind not in SERVICE_KINDS:
        raise ValueError(f"{profile}: вид модели {model.kind} не поддержан сервисом")
    metrics = read_json(REPORTS / "metrics" / "concentration" / report / f"{profile}.json")
    service = metrics["service"]
    if service["deployed_model"] != meta["service"]["model"]:
        raise ValueError(f"{profile}: модель в meta.json и в отчёте различаются")
    table = features[features["measurement_profile"] == profile]
    constant = float(model.fitted) if model.kind == "median" else None
    baseline, deployed = service["baseline"], service["deployed"]
    nested = service["nested_procedure"]
    payload: dict[str, Any] = {
        "profile": profile,
        "target_key": meta["target_key"],
        "unit": "items/km2",
        "model": service["deployed_model"],
        "kind": model.kind,
        "features": meta["service"]["features"],
        "params": model.params,
        "gain_over_median": service["gain_over_median"],
        "reason": service_reason(profile, service, constant),
        "reference": meta["domain"]["reference"],
        "domain": meta["domain"],
        "conformal": {
            **service["coverage"],
            "log_quantile": service["log_quantile"],
            "quantile_definition": service["quantile_definition"],
        },
        "points": np.column_stack([table["x_km"], table["y_km"], table["concentration"]])
        .round(4)
        .tolist(),
        "validation": {
            "events": metrics["events"],
            "survey_days": metrics["survey_days"],
            "repetitions": service["repetitions"],
            "scheme": metrics["validation"]["outer"],
            "rule": service["rule"],
            "confidence": service["confidence"],
            "model_mae": deployed["mae"]["mean"],
            "model_mae_sd": deployed["mae"]["sd"],
            "model_rmse": deployed["rmse"]["mean"],
            "model_rmse_sd": deployed["rmse"]["sd"],
            "model_coverage": deployed["coverage"]["mean"],
            "baseline_mae": baseline["mae"]["mean"],
            "baseline_mae_sd": baseline["mae"]["sd"],
            "baseline_rmse": baseline["rmse"]["mean"],
            "baseline_rmse_sd": baseline["rmse"]["sd"],
            "baseline_coverage": baseline["coverage"]["mean"],
            "candidates": {
                label: _candidate_summary(row) for label, row in service["candidates"].items()
            },
            "nested_procedure": {
                "selection": nested["selection"],
                "mae": nested["nested"]["mae"]["mean"],
                "mae_sd": nested["nested"]["mae"]["sd"],
                "rmse": nested["nested"]["rmse"]["mean"],
                "rmse_sd": nested["nested"]["rmse"]["sd"],
                "difference_mae": nested["difference_vs_median"]["mae"],
            },
        },
    }
    if model.kind == "tweedie":
        payload["glm"] = _tweedie(model)
    if model.kind == "median":
        payload["constant"] = constant
    write_json(MODELS / "concentration" / "service" / f"{profile}.json", payload)
    return payload


def export_service_models(config: dict[str, Any]) -> list[dict]:
    features = load_features(config)
    report = config["report_name"]
    return [export_profile(report, profile, features) for profile in config["profiles"]]
