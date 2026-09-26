import json
import os
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.analysis.detector import OnnxDetector
from app.analysis.models import UnavailableDetector
from app.core.config import Settings
from app.main import create_app

SERVICE = "raunet__marida_mixed__common"
CI = {"precision": [0.74, 0.92], "recall": [0.93, 1.0], "f1": [0.83, 0.95], "iou": [0.71, 0.9]}


@pytest.fixture(autouse=True)
def without_onnx_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        OnnxDetector, "load", classmethod(lambda cls, folder: UnavailableDetector())
    )


def split(f1: float, positives: int = 299, pixels: int = 180209) -> dict[str, Any]:
    return {
        "threshold": 0.16,
        "pixels": pixels,
        "positives": positives,
        "tp": 290,
        "fp": 57,
        "fn": 9,
        "tn": pixels - 356,
        "precision": 0.8357,
        "recall": 0.9699,
        "f1": f1,
        "iou": 0.8146,
        "pr_auc": 0.9764,
        "false_positives_by_class": {
            "waves": {"pixels": 1865, "false_positives": 14, "false_positive_rate": 0.0075},
            "ship": {"pixels": 1163, "false_positives": 24, "false_positive_rate": 0.0206},
            "marine_water": {"pixels": 18869, "false_positives": 0, "false_positive_rate": 0.0},
        },
        "by_group": {"12-12-20_16PCC": {}, "14-9-18_16PCC": {}},
    }


def run(name: str, f1: float, **extra: Any) -> dict[str, Any]:
    return {
        "name": name,
        "config": {
            "name": name.split("__")[0],
            "data": "marida_mixed",
            "split": "common",
            "input": {"indices": True},
            "model": {"kind": "raunet"},
            "loss": {"kind": "bce_dice"},
        },
        "data": "marida_mixed",
        "threshold": 0.15921,
        "threshold_source": "val_max_f1",
        "val": split(0.9429, positives=1068, pixels=213080),
        "test": split(f1),
        "test_ci95_scene_bootstrap": CI,
        "val_ci95_scene_bootstrap": CI,
        "test_unlabeled_alarms": {"alarm_pixels_per_100km2": 247.4},
        "tta": {"used": True},
        "postprocessing": {
            "chosen": {"scl": False, "ship_veto": None, "min_pixels": 2, "threshold": 0.15921},
            "test": {"precision": 0.8559, "recall": 0.9532, "f1": 0.9019, "iou": 0.8213},
        },
        **extra,
    }


def write(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def concentration_block() -> dict[str, Any]:
    return {
        "events": 63,
        "survey_days": 26,
        "research": {"role": "primary", "selection": "вложенный выбор"},
        "nested": {
            "mae": {"mean": 30.79, "sd": 3.32},
            "rmse": {"mean": 43.72, "sd": 5.24},
            "coverage": {"mean": 0.75, "sd": 0.06},
        },
        "baseline": {"mae": {"mean": 34.11, "sd": 0.61}, "rmse": {"mean": 47.4, "sd": 0.63}},
        "difference_vs_median": {
            "mae": {"mean": -3.31, "confidence": 0.95, "ci": [-9.28, 3.76]},
            "rmse": {"mean": -3.67, "confidence": 0.95, "ci": [-11.77, 6.43]},
        },
        "gain_over_median": False,
    }


@pytest.fixture
def artifacts(tmp_path: Path) -> tuple[Path, Path]:
    reports, models = tmp_path / "reports", tmp_path / "models"
    detector = reports / "metrics" / "detector"
    write(detector / f"{SERVICE}.json", run(SERVICE, 0.8978))
    write(
        detector / "lgbm_pixel__marida_l2a__common.json",
        run("lgbm_pixel__marida_l2a__common", 0.9048, features=["B08", "B11", "FDI"]),
    )
    write(
        detector / "raunet__marida__on_marida_l2a__common.json",
        run(
            "raunet__marida__on_marida_l2a__common",
            0.7984,
            frozen_threshold_from="raunet__marida",
            config={"source_run": "raunet__marida", "data": "marida_l2a", "split": "common"},
        ),
    )
    write(detector / "summary.json", [{"run": SERVICE}])
    write(
        detector / "regions" / "lgbm_pixel__marida_l2a.json",
        {
            "name": "lgbm_pixel__marida_l2a",
            "protocol": "регион целиком в тесте",
            "regions": {
                "scotland": {"positives": 27, "precision": 0, "recall": 0, "f1": 0, "iou": 0},
                "honduras": {
                    "positives": 1061,
                    "precision": 0.28,
                    "recall": 0.77,
                    "f1": 0.41,
                    "iou": 0.26,
                },
            },
            "pooled": {"precision": 0.48, "recall": 0.76, "f1": 0.59, "iou": 0.42},
        },
    )
    write(
        detector / "external" / f"black_sea_negatives__{SERVICE}.json",
        {
            "run": SERVICE,
            "collection": "sentinel-2-l2a",
            "definition": "доля пикселей выше порога",
            "by_class": {
                "ship": {"polygons": 7, "pixels": 455, "area_km2": 0.0455, "alarm_pixels": 1},
                "cloud": {"polygons": 8, "pixels": 203317, "area_km2": 20.33, "alarm_pixels": 0},
            },
            "scenes": [
                {
                    "aoi": "novorossiysk",
                    "scene_id": "S2A",
                    "pixels": 100,
                    "detected_pixels": 5,
                    "zones": 2,
                }
            ],
        },
    )
    rate = {"detected": 1, "detection_rate": 0.25, "detection_rate_ci95": [0.05, 0.7]}
    write(
        detector / "external" / "plp.json",
        {
            "description": "мишени PLP",
            "protocol": {"threshold": "замороженный порог"},
            "summary": {
                "targets": 53,
                "usable": 53,
                "plastic_or_mixed": {"targets": 37, "detected": 6, "detection_rate": 0.162},
                "natural_controls": {"targets": 16, "detected": 1, "detection_rate": 0.0625},
                "by_size": {
                    "≥20 м": {"targets": 22, **rate},
                    "5–10 м": {"targets": 10, **rate},
                    "<5 м": {"targets": 4, **rate},
                },
                "background": {
                    "windows": 27,
                    "window_water_km2": 82.9,
                    "window_zones": 9,
                    "window_zones_per_100_km2": 10.9,
                    "ring_km2": 4.9,
                    "alarm_pixels": 0,
                },
            },
        },
    )
    splits = reports / "splits" / "detector_marida.csv"
    splits.parent.mkdir(parents=True)
    splits.write_text(
        "name,official_split,common_split\na,test,test\nb,test,none\nc,val,test\n", encoding="utf-8"
    )
    write(
        models / "detector" / "service" / "detector.json",
        {
            "name": SERVICE,
            "bands": ["B02", "B03", "B04", "B08"],
            "threshold": 0.15921,
            "min_pixels": 2,
            "sea_mask": {"rule": "вода по SCL"},
            "test_metrics": {"precision": 0.8357, "recall": 0.9699, "f1": 0.8978, "iou": 0.8146},
            "test_ci95": CI,
        },
    )
    concentration = reports / "metrics" / "concentration"
    for report in ("broad", "compact"):
        write(
            concentration / report / "summary.json",
            {
                "report": report,
                "repetitions": 10,
                "profiles": {"S2_visual_GT2": concentration_block()},
            },
        )
    write(
        concentration / "satellite_pairs.json",
        {
            "detector": SERVICE,
            "events": 7,
            "correlations": {"fdi_mean": {"spearman": -0.43, "p_value": 0.34}},
        },
    )
    write(
        models / "concentration" / "service" / "S2_visual_GT2.json",
        {
            "profile": "S2_visual_GT2",
            "target_key": "plastic-visual",
            "unit": "items/km2",
            "model": "median",
            "kind": "median",
            "gain_over_median": False,
            "reason": "значимого выигрыша над медианой нет",
            "constant": 36.09,
            "conformal": {"nominal": 0.8, "empirical": 0.819},
            "validation": {"rule": "кандидат против медианы"},
        },
    )
    return reports, models


def client_for(settings: Settings, reports: Path, models: Path) -> TestClient:
    local = settings.model_copy(update={"reports_dir": reports, "models_dir": models})
    return TestClient(create_app(local))


def test_models_report_reads_evaluation_artifacts(
    settings: Settings, artifacts: tuple[Path, Path]
) -> None:
    with client_for(settings, *artifacts) as client:
        response = client.get("/api/v1/models")

    assert response.status_code == 200
    body = response.json()
    detector = body["detector"]
    assert detector["service"]["name"] == SERVICE
    assert detector["service"]["sea_mask"] == "вода по SCL"
    assert detector["test_set"] == {
        "dataset": "MARIDA",
        "data": "marida_mixed",
        "split": "common",
        "patches": 2,
        "scenes": 2,
        "pixels": 180209,
        "positives": 299,
    }
    runs = {item["name"]: item for item in detector["runs"]}
    assert set(runs) == {SERVICE, "lgbm_pixel__marida_l2a__common"}
    served = runs[SERVICE]
    assert served["in_service"] is True
    assert served["test"]["metrics"]["f1"] == 0.8978
    assert served["test"]["ci95"]["f1"] == [0.83, 0.95]
    assert served["val"]["metrics"]["f1"] == 0.9429
    assert served["tta"] is True
    assert served["postprocessing"]["min_pixels"] == 2
    assert served["postprocessing"]["test"]["f1"] == 0.9019
    assert served["unlabeled_alarms_per_100km2"] == 247.4
    assert [row["label"] for row in served["test"]["false_positives_by_class"]] == [
        "ship",
        "waves",
        "marine_water",
    ]
    assert served["inputs"] is None
    assert runs["lgbm_pixel__marida_l2a__common"]["inputs"] == ["B08", "B11", "FDI"]
    assert runs["lgbm_pixel__marida_l2a__common"]["in_service"] is False

    checks = detector["checks"]
    assert [item["source_run"] for item in checks["domain_shift"]] == ["raunet__marida"]
    assert checks["domain_shift"][0]["method"] == "raunet__marida"
    regions = checks["leave_region_out"][0]
    assert [item["region"] for item in regions["regions"]] == ["honduras", "scotland"]
    assert regions["pooled"]["f1"] == 0.59
    negatives = checks["black_sea_negatives"]
    assert negatives["pixels"] == 203772
    assert negatives["alarm_pixels"] == 1
    assert negatives["scenes"][0]["zones"] == 2
    plp = checks["plp"]
    assert [item["group"] for item in plp["groups"]] == ["plastic_or_mixed", "natural_controls"]
    assert plp["groups"][0]["ci95"] is None
    assert [item["group"] for item in plp["by_size"]] == ["<5 м", "5–10 м", "≥20 м"]
    assert plp["background"]["zones"] == 9

    profile = body["concentration"]["profiles"][0]
    assert profile["profile"] == "S2_visual_GT2"
    assert profile["target_key"] == "plastic-visual"
    assert profile["events"] == 63
    assert [item["report"] for item in profile["evaluations"]] == ["broad", "compact"]
    assert profile["evaluations"][0]["difference_mae"]["ci"] == [-9.28, 3.76]
    assert profile["evaluations"][0]["nested_coverage"]["mean"] == 0.75
    assert profile["served"]["model"] == "median"
    assert profile["served"]["coverage_empirical"] == 0.819
    assert body["concentration"]["satellite_link"]["events"] == 7

    drift = body["drift"]
    assert drift["status"] == "scenario"
    assert drift["members"] == len(drift["windages"]) * len(drift["stokes"]) * drift["particles"]
    assert drift["horizons_h"][-1] == drift["max_hours"]

    assert "reports/metrics/detector/summary.json" not in body["sources"]
    assert f"reports/metrics/detector/{SERVICE}.json" in body["sources"]
    assert "models/detector/service/detector.json" in body["sources"]
    assert all(not source.startswith("/") for source in body["sources"])


def test_meta_reports_model_evaluation_when_artifacts_exist(
    settings: Settings, artifacts: tuple[Path, Path]
) -> None:
    with client_for(settings, *artifacts) as client:
        statuses = {
            item["key"]: item["status"]
            for item in client.get("/api/v1/meta").json()["capabilities"]
        }

    assert statuses["model_evaluation"] == "available"


def test_models_report_follows_artifact_changes(
    settings: Settings, artifacts: tuple[Path, Path]
) -> None:
    reports, models = artifacts
    path = reports / "metrics" / "detector" / f"{SERVICE}.json"
    with client_for(settings, reports, models) as client:
        evaluation = client.app.state.evaluation
        first = evaluation.load()
        assert evaluation.load() is first

        write(path, run(SERVICE, 0.91))
        stamp = path.stat().st_mtime_ns + 1_000_000_000
        os.utime(path, ns=(stamp, stamp))
        body = client.get("/api/v1/models").json()

    served = next(item for item in body["detector"]["runs"] if item["in_service"])
    assert served["test"]["metrics"]["f1"] == 0.91


def test_models_report_skips_broken_artifacts(
    settings: Settings, artifacts: tuple[Path, Path]
) -> None:
    reports, models = artifacts
    detector = reports / "metrics" / "detector"
    (detector / "broken.json").write_text("{", encoding="utf-8")
    write(detector / "partial.json", {"name": "partial", "data": "marida"})
    with client_for(settings, reports, models) as client:
        body = client.get("/api/v1/models").json()

    names = {item["name"] for item in body["detector"]["runs"]}
    assert names == {SERVICE, "lgbm_pixel__marida_l2a__common"}
    assert "reports/metrics/detector/partial.json" not in body["sources"]


def test_models_report_without_artifacts_is_not_implemented(
    tmp_path: Path, settings: Settings
) -> None:
    with client_for(settings, tmp_path / "reports", tmp_path / "models") as client:
        response = client.get("/api/v1/models")
        statuses = {
            item["key"]: item["status"]
            for item in client.get("/api/v1/meta").json()["capabilities"]
        }

    assert response.status_code == 501
    assert response.json()["error"]["code"] == "not_implemented"
    assert statuses["model_evaluation"] == "planned"


def test_printable_report_carries_the_artifact_numbers(
    settings: Settings, artifacts: tuple[Path, Path]
) -> None:
    reports, models = artifacts
    with client_for(settings, reports, models) as client:
        response = client.get("/api/v1/models/report.html")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    body = response.text
    assert "Сводка · сервисный детектор" in body
    assert "<link" not in body and 'src="http' not in body


def test_zone_flag_checks_come_from_the_flag_reports(
    settings: Settings, artifacts: tuple[Path, Path]
) -> None:
    reports, models = artifacts
    folder = reports / "metrics" / "detector" / "flags"
    folder.mkdir(parents=True)
    shares = {
        "debris": {"zones": 157, "flagged": 13, "share": 0.083},
        "ship": {"zones": 7, "flagged": 2, "share": 0.29},
        "other_labeled": {"zones": 7, "flagged": 4, "share": 0.57},
        "unlabeled": {"zones": 1210, "flagged": 452, "share": 0.37},
    }
    block = {
        "part": "test",
        "agreement_auc": 0.66,
        "agreement_auc_ci95": [0.46, 0.85],
        "probability_auc": 0.9,
        "probability_auc_ci95": None,
        "agreement_auc_within_probability": 0.61,
        "agreement_auc_within_probability_ci95": [0.44, 0.83],
        "flag_shares": shares,
    }
    (folder / "stability.json").write_text(
        json.dumps(
            {
                "rule": {"cutoff": 0.849, "quantile": 0.05, "views": 8, "flag": False},
                "fit": {**block, "part": "val"},
                "test": block,
            }
        ),
        encoding="utf-8",
    )
    with client_for(settings, reports, models) as client:
        checks = client.get("/api/v1/models").json()["detector"]["checks"]["zone_flags"]

    assert [check["kind"] for check in checks] == ["unstable"]
    check = checks[0]
    assert check["in_service"] is False
    assert "флаг выключен" in check["rule"]
    merged = [row for row in check["shares"] if row["part"] == "test"]
    assert [(row["group"], row["flagged"], row["objects"]) for row in merged] == [
        ("обломки", 13, 157),
        ("ложные размеченные", 6, 14),
        ("неразмеченные", 452, 1210),
    ]
    assert check["discrimination"][0]["ci95"] == [0.46, 0.85]


def test_c1_check_is_a_collection_block_not_a_run(
    settings: Settings, artifacts: tuple[Path, Path]
) -> None:
    reports, models = artifacts
    item = {
        "patches": 116,
        "scenes": 5,
        "c1": {"f1": 0.947},
        "c1_f1_ci95": [0.85, 0.99],
        "l2a": {"f1": 0.948},
        "l2a_f1_ci95": [0.86, 0.99],
        "c1_minus_l2a_f1": -0.002,
        "c1_minus_l2a_f1_ci95": [-0.072, 0.047],
    }
    payload = {
        "alignment": {
            "scenes_with_data": 35,
            "scenes_aligned": 8,
            "scenes_tolerant": 28,
            "subpixel_shift_median_px": 0.47,
        },
        "selection_rule": "объектный F1 на объединённой val",
        "chosen": SERVICE,
        "runs": {SERVICE: {"val": {"tolerant": item, "strict": {"patches": 0}}, "test": {}}},
    }
    path = reports / "metrics" / "detector" / "c1_check.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with client_for(settings, reports, models) as client:
        detector = client.get("/api/v1/models").json()["detector"]

    assert all(run["name"] != "c1_check" for run in detector["runs"])
    collection = detector["checks"]["collection"]
    assert collection["alignment"].startswith("C1 есть для 35 сцен MARIDA; точно совмещены")
    assert "0,47 пикс." in collection["alignment"]
    assert [(row["part"], row["in_service"], row["patches"]) for row in collection["rows"]] == [
        ("val", True, 116)
    ]


def test_figures_are_served_only_from_the_whitelist(settings: Settings) -> None:
    local = settings.model_copy(
        update={
            "reports_dir": Path(__file__).resolve().parents[2] / "reports",
            "models_dir": Path(__file__).resolve().parents[2] / "models",
        }
    )
    with TestClient(create_app(local)) as client:
        assert client.get("/api/v1/models/figures/plp").headers["content-type"] == "image/png"
        assert client.get("/api/v1/models/figures/best").status_code == 200
        assert client.get("/api/v1/models/figures/..%2Fsecret").status_code == 404
        assert client.get("/api/v1/models/figures/unknown").status_code == 404
