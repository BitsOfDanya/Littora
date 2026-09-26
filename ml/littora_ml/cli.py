from __future__ import annotations

import argparse

from littora_ml.audit.case_audit import run_audit
from littora_ml.common.config import load_config
from littora_ml.common.paths import resolve


def _audit(_: argparse.Namespace) -> None:
    audit = run_audit()
    print(f"строк {audit['dataset']['rows']}, событий {audit['dataset']['events']}")
    for row in audit["profiles"]:
        stats = row["concentration_items_km2"] or {}
        print(
            f"  {row['measurement_profile']:<18} {row['target_scope']:<26} "
            f"событий {row['events']:<4} медиана {stats.get('median')} "
            f"пары {row['satellite_pairing']}"
        )
    roles = audit["leakage"]["roles"]
    print("запрещены как утечка:", ", ".join(sorted(roles.get("forbidden_leakage", []))))


def _detector_prepare(args: argparse.Namespace) -> None:
    from littora_ml.detector.dataset import build_marida_cache
    from littora_ml.detector.l2a import build_l2a_cache

    config = load_config(args.config)
    marida_cache = resolve(config["marida"]["cache"])
    if args.variant in ("marida", "all"):
        build_marida_cache(resolve(config["marida"]["root"]), marida_cache)
        print(f"MARIDA: {marida_cache}")
    if args.variant in ("l2a", "all"):
        l2a = config["l2a"]
        summary = build_l2a_cache(
            marida_cache,
            resolve(l2a["cache"]),
            l2a["catalog"],
            l2a["collections"],
            l2a["workers"],
            l2a.get("min_alignment", 0.97),
        )
        print(f"L2A: найдено {summary['patches_found']} из {summary['patches']} патчей")
    if args.variant in ("c1", "all"):
        c1 = config["c1"]
        summary = build_l2a_cache(
            marida_cache,
            resolve(c1["cache"]),
            c1["catalog"],
            c1["collections"],
            c1["workers"],
            c1.get("min_alignment", 0.97),
        )
        print(f"C1: найдено {summary['patches_found']} из {summary['patches']} патчей")
    if args.variant in ("review", "all"):
        from littora_ml.detector.review_patches import build_review_cache

        review = config["review"]
        summary = build_review_cache(
            resolve(review["source"]),
            resolve(review["cache"]),
            review["catalog"],
            review["collections"],
            review.get("min_confidence", 2),
        )
        print(
            f"отметки команды: зон {summary['zones_used']}, окон {summary['patches']}, "
            f"пикселей {summary['labeled_pixels']}"
        )
    if args.variant in ("mixed", "all"):
        from littora_ml.detector.dataset import build_mixed_cache

        build_mixed_cache(
            marida_cache, resolve(config["l2a"]["cache"]), resolve(DATA_VARIANTS["marida_mixed"])
        )
        print("смешанный набор: MARIDA + L2A для обучения, проверка на L2A")
    if args.variant in ("mixed_c1", "all"):
        from littora_ml.detector.dataset import build_mixed_cache

        extra = [(resolve(config["c1"]["cache"]), "c1")]
        if (resolve(config["review"]["cache"]) / "patches.parquet").exists():
            extra.append((resolve(config["review"]["cache"]), "review"))
        build_mixed_cache(
            marida_cache,
            resolve(config["l2a"]["cache"]),
            resolve(config["mixed_c1"]["cache"]),
            extra,
        )
        print("смешанный набор c1: MARIDA, L2A, C1 и отметки команды; проверка на L2A")


DATA_VARIANTS = {
    "marida": "data/processed/detector/marida",
    "marida_l2a": "data/processed/detector/marida_l2a",
    "marida_mixed": "data/processed/detector/marida_mixed",
    "marida_c1": "data/processed/detector/marida_c1",
    "marida_mixed_c1": "data/processed/detector/marida_mixed_c1",
}


def _detector_split(patches, name: str):
    import pandas as pd

    from littora_ml.detector.splits import official, region_holdout

    if name == "official":
        return official(patches.table)
    if name == "common":
        if "source" in patches.table:
            return official(patches.table)
        if "l2a_found" in patches.table:
            return official(patches.table).where(patches.table["l2a_found"].to_numpy(), "none")
        found = pd.read_parquet(resolve(DATA_VARIANTS["marida_l2a"]) / "patches.parquet")
        return official(patches.table).where(found["l2a_found"].to_numpy(), "none")
    if name.startswith("holdout:"):
        return region_holdout(patches.table, tuple(name.split(":", 1)[1].split(",")))
    raise ValueError(f"неизвестное разбиение {name}")


def _detector_baseline(args: argparse.Namespace) -> None:
    import joblib

    from littora_ml.common.paths import MODELS
    from littora_ml.common.seed import fix_seed
    from littora_ml.detector.baselines import (
        fdi_probability,
        rule_scorer,
        run_tree_baseline,
        tune_rule,
    )
    from littora_ml.detector.dataset import load_patch_set
    from littora_ml.detector.evaluation import report, save_run, score_patches
    from littora_ml.detector.postprocess import postprocessing_report

    config = load_config(args.config)
    data = args.data or config["data"]
    split_name = args.split or config["split"]
    config["data"], config["split"] = data, split_name
    fix_seed(config.get("seed", 42))
    patches = load_patch_set(resolve(DATA_VARIANTS[data]))
    split = _detector_split(patches, split_name)
    suffix = (
        "" if split_name == "official" else "__" + split_name.replace(":", "-").replace(",", "+")
    )
    name = f"{config['name']}__{data}{suffix}"
    max_confidence_code = config.get("labels", {}).get("max_confidence_code", 3)
    values = split.to_numpy()
    if config["model"]["kind"] in ("fdi", "fdi_rule"):
        extra, model = {}, None
        scorer = fdi_probability()
        if config["model"]["kind"] == "fdi_rule":
            rule = tune_rule(patches, (values == "val").nonzero()[0], max_confidence_code)
            scorer = rule_scorer(rule["ndvi_max"], rule["blue_max"])
            extra = {"rule": rule}
        val_scores = score_patches(scorer, patches, (values == "val").nonzero()[0])
        test_scores = score_patches(scorer, patches, (values == "test").nonzero()[0])
    else:
        extra, val_scores, test_scores, model = run_tree_baseline(patches, split, config)
    extra["postprocessing"] = postprocessing_report(
        patches, split, val_scores, test_scores, max_confidence_code
    )
    result = report(
        name, config, patches, split, val_scores, test_scores, max_confidence_code, extra
    )
    path = save_run(result, test_scores, patches, split, val_scores)
    if model is not None:
        folder = MODELS / "detector" / name
        folder.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, folder / "model.joblib")
    test = result["test"]
    print(
        f"{name}: порог {result['threshold']:.4f} · test P {test['precision']:.3f} "
        f"R {test['recall']:.3f} F1 {test['f1']:.3f} IoU {test['iou']:.3f} · val F1 "
        f"{result['val']['f1']:.3f} · {path}"
    )


def _detector_train(args: argparse.Namespace) -> None:
    from littora_ml.common.seed import fix_seed
    from littora_ml.detector.dataset import load_patch_set
    from littora_ml.detector.evaluation import report, save_run
    from littora_ml.detector.postprocess import postprocessing_report
    from littora_ml.detector.train import train_detector

    config = load_config(args.config)
    data = args.data or config["data"]
    split_name = args.split or config["split"]
    config["data"], config["split"] = data, split_name
    if args.epochs:
        config["train"]["epochs"] = args.epochs
    fix_seed(config.get("seed", 42))
    patches = load_patch_set(resolve(DATA_VARIANTS[data]))
    split = _detector_split(patches, split_name)
    tag = split_name.replace(":", "-").replace(",", "+")
    suffix = "" if split_name == "official" else f"__{tag}"
    name = args.name or f"{config['name']}__{data}{suffix}"
    max_confidence_code = config.get("labels", {}).get("max_confidence_code", 3)
    extra, val_scores, test_scores, _ = train_detector(patches, split, config, name)
    extra["postprocessing"] = postprocessing_report(
        patches, split, val_scores, test_scores, max_confidence_code
    )
    result = report(
        name, config, patches, split, val_scores, test_scores, max_confidence_code, extra
    )
    path = save_run(result, test_scores, patches, split, val_scores)
    test = result["test"]
    print(
        f"{name}: эпох {extra['epochs_run']} (лучшая {extra['best_epoch']}), порог "
        f"{result['threshold']:.3f} · test P {test['precision']:.3f} R {test['recall']:.3f} "
        f"F1 {test['f1']:.3f} IoU {test['iou']:.3f} · val F1 {result['val']['f1']:.3f} · {path}"
    )


def _concentration_run(args: argparse.Namespace) -> None:
    from littora_ml.common.seed import fix_seed
    from littora_ml.concentration.run import run_experiment

    config = load_config(args.config)
    if args.jobs:
        config["jobs"] = args.jobs
    fix_seed(config["seed"])
    summary = run_experiment(config, refresh=args.refresh)
    from littora_ml.concentration.figures import profile_figure

    for profile in config["profiles"]:
        profile_figure(config["report_name"], profile)

    def band(values: dict) -> str:
        digits = 2 if values["mean"] <= 1 else 1
        return f"{values['mean']:.{digits}f} ± {values['sd']:.{digits}f}"

    def ci(values: dict) -> str:
        low, high = values["ci"]
        return f"{values['mean']:+.1f} [{low:+.1f}; {high:+.1f}]"

    print(
        f"{config['report_name']}: {summary['repetitions']} повторов вложенной CV по дням съёмки; "
        f"{summary['research']['selection']}"
    )
    for profile, row in summary["profiles"].items():
        nested, baseline = row["nested"], row["baseline"]
        service, best, season = row["service"], row["best_config"], row["season_check"]
        rivals = ", ".join(
            f"{label} {ci(entry['difference_mae'])}"
            for label, entry in service["candidates"].items()
        )
        with_season, without_season = season["with_season"], season["without_season"]
        print(
            f"{profile:<18} событий {row['events']:<3} | вложенная CV MAE {band(nested['mae'])} "
            f"RMSE {band(nested['rmse'])}, покрытие {band(nested['coverage'])} | медиана MAE "
            f"{band(baseline['mae'])} RMSE {band(baseline['rmse'])} | разница MAE "
            f"{ci(row['difference_vs_median']['mae'])} (95 % ДИ)"
        )
        print(
            f"{'':<18} сервис: кандидаты против медианы ({service['confidence']:.1%} ДИ) "
            f"{rivals} → {service['deployed_model']}, покрытие "
            f"{service['coverage']['empirical']:.2f}"
        )
        if with_season and without_season:
            print(
                f"{'':<18} сезон на поздних днях: с сезоном {with_season['selected']} MAE "
                f"{with_season['holdout_mae']:.1f}, без сезона {without_season['selected']} MAE "
                f"{without_season['holdout_mae']:.1f}"
            )
        print(f"{'':<18} {best['selection']}: {best['label']} MAE {best['mae']['mean']:.1f}")


def _concentration_external(args: argparse.Namespace) -> None:
    from littora_ml.common.seed import fix_seed
    from littora_ml.concentration.external import run_external
    from littora_ml.concentration.external_figures import external_figures

    config = load_config(args.config)
    if args.jobs:
        config["jobs"] = args.jobs
    if args.bootstrap:
        config["bootstrap"] = args.bootstrap
    fix_seed(config["seed"])
    run = run_external(config, refresh=args.refresh)
    summary = run["summary"]

    def cell(row: dict, key: str) -> str:
        value = row.get(key)
        if value is None:
            return "—"
        return f"{value:.2f}" if key.startswith("spearman") else f"{value:.0f}"

    for name, block in summary["designs"].items():
        print(f"{name}: тест {block['test_rows']} строк, групп {block['test_groups']}")
        labels = ("median", "site_climatology", "idw_k5", "nested", "models_only")
        for label in (*labels, "with_weather", "without_weather"):
            if label not in block:
                continue
            row = block[label]
            low, high = row["mae_ci"]
            print(
                f"  {label:<17} MAE {cell(row, 'mae'):>5} [{low:.0f}; {high:.0f}] RMSE "
                f"{cell(row, 'rmse'):>5} log1p {row['mae_log1p']:.2f} Spearman "
                f"{cell(row, 'spearman'):>5} (в фолдах {cell(row, 'spearman_within_folds'):>5}) "
                f"смещение {row['bias']:+.0f} уровень "
                f"×{row['geometric_ratio']:.2f}"
            )
    print(summary["service"]["decision"])
    for path in external_figures(run, config):
        print(path)


def _detector_evaluate(args: argparse.Namespace) -> None:
    from littora_ml.common.io import file_sha256
    from littora_ml.detector.dataset import load_patch_set
    from littora_ml.detector.evaluation import report, save_run, score_patches
    from littora_ml.detector.inference import OnnxDetector, TrainedDetector, run_threshold

    patches = load_patch_set(resolve(DATA_VARIANTS[args.data]))
    split = _detector_split(patches, args.split)
    values = split.to_numpy()
    if args.onnx:
        onnx = resolve(args.onnx)
        scorer = OnnxDetector(onnx).scorer()
        threshold = None
        source = args.name or onnx.stem
        config = {"source_onnx_sha256": file_sha256(onnx), "data": args.data, "split": args.split}
        extra = {"contract": "reflectance (N, 11, H, W) в порядке BANDS -> probability (N, H, W)"}
    else:
        threshold, tta = run_threshold(args.run)
        scorer = TrainedDetector(args.run).scorer(tta)
        source = args.run
        config = {"source_run": args.run, "data": args.data, "split": args.split}
        extra = {"frozen_threshold_from": args.run, "tta": {"used": tta}}
    val_scores = score_patches(scorer, patches, (values == "val").nonzero()[0])
    test_scores = score_patches(scorer, patches, (values == "test").nonzero()[0])
    name = f"{source}__on_{args.data}__{args.split}"
    result = report(
        name, config, patches, split, val_scores, test_scores, extra=extra, threshold=threshold
    )
    save_run(result, test_scores, patches, split, val_scores)
    test = result["test"]
    origin = "замороженный" if threshold is not None else "выбран на val"
    print(
        f"{name}: порог {result['threshold']:.3f} ({origin}) · test P {test['precision']:.3f} "
        f"R {test['recall']:.3f} F1 {test['f1']:.3f} IoU {test['iou']:.3f}"
    )


def _splits(_: argparse.Namespace) -> None:
    from littora_ml.splits_export import concentration_splits, export_detector_splits

    concentration = concentration_splits()
    detector = export_detector_splits()
    runs = concentration.groupby("report")["repetition"].nunique().to_dict()
    print(f"детектор: {len(detector)} патчей; концентрация: повторов по отчётам {runs}")


def _concentration_export(args: argparse.Namespace) -> None:
    from littora_ml.concentration.export import export_service_models

    for payload in export_service_models(load_config(args.config)):
        print(
            f"{payload['profile']:<18} {payload['model']:<22} покрытие "
            f"{payload['conformal']['empirical']:.2f} · {payload['reason']}"
        )


def _detector_export(args: argparse.Namespace) -> None:
    from littora_ml.detector.export import export_detector

    manifest = export_detector(args.run, args.max_pixels)
    print(
        f"ONNX: {manifest['name']} порог {manifest['threshold']:.3f}, "
        f"расхождение с torch {manifest['onnx_max_abs_difference']:.2e}"
    )


def _detector_report(args: argparse.Namespace) -> None:
    from littora_ml.detector.dataset import load_patch_set
    from littora_ml.detector.figures import examples
    from littora_ml.detector.summary import detector_summary

    frame = detector_summary()
    columns = ["run", "val_f1", "test_precision", "test_recall", "test_f1", "test_iou"]
    print(frame[columns].to_string(index=False))
    for run in args.figures or []:
        name, data, split = run.split(":")
        patches = load_patch_set(resolve(DATA_VARIANTS[data]))
        for path in examples(name, patches, _detector_split(patches, split)):
            print(path)


def _detector_regions(args: argparse.Namespace) -> None:
    from littora_ml.detector.dataset import load_patch_set
    from littora_ml.detector.regions import run_regions

    config = load_config(args.config)
    data = args.data or config["data"]
    if args.jobs:
        config["model"]["n_jobs"] = args.jobs
    patches = load_patch_set(resolve(DATA_VARIANTS[data]))
    base = _detector_split(patches, "common" if data != "marida" else "official")
    result = run_regions(patches, base, config, f"{config['name']}__{data}")
    for region, row in result["regions"].items():
        print(f"  {region:<16} пикс. {row['positives']:<5} F1 {row['f1']:.3f} IoU {row['iou']:.3f}")
    print(f"  сводно F1 {result['pooled']['f1']:.3f} IoU {result['pooled']['iou']:.3f}")


def _detector_predict(args: argparse.Namespace) -> None:
    from littora_ml.common.paths import REPORTS
    from littora_ml.detector.predict import predict_scene

    bbox = tuple(float(value) for value in args.bbox.split(","))
    out = REPORTS / "predictions" / "scenes" / args.scene
    meta = predict_scene(args.run, args.collection, args.scene, bbox, out)
    print(
        f"{args.scene}: зон {meta['zones']}, пикселей выше порога {meta['detected_pixels']} · {out}"
    )


def _concentration_satellite(args: argparse.Namespace) -> None:
    from littora_ml.concentration.dataset import modeling_table
    from littora_ml.satellite.pairs import pair_study

    scorer, threshold = None, None
    if args.run:
        from littora_ml.detector.inference import TrainedDetector, run_postprocessing, run_threshold

        _, tta = run_threshold(args.run)
        threshold = run_postprocessing(args.run)["threshold"]
        scorer = TrainedDetector(args.run).scorer(tta)
    table = modeling_table()
    study = pair_study(table, scorer, threshold, args.run or "")
    if scorer is not None:
        from littora_ml.satellite.figures import pairs_figure

        values = dict(zip(table["sample_id"], table["concentration"], strict=True))
        print(pairs_figure(scorer, threshold, values, args.run))
    for name, row in study["correlations"].items():
        print(f"  {name:<18} Spearman {row['spearman']:+.2f} (p {row['p_value']:.3f})")


def _detector_ensemble(args: argparse.Namespace) -> None:
    from littora_ml.detector.dataset import load_patch_set
    from littora_ml.detector.ensemble import run_ensemble
    from littora_ml.detector.evaluation import report, save_run
    from littora_ml.detector.postprocess import postprocessing_report

    runs = args.runs.split(",")
    patches = load_patch_set(resolve(DATA_VARIANTS[args.data]))
    split = _detector_split(patches, args.split)
    val_scores, test_scores, best, search = run_ensemble(runs, patches, split)
    name = "ensemble__" + "+".join(runs)
    config = {"members": runs, "data": args.data, "split": args.split}
    extra = {"weights": best["weights"], "weight_search": search}
    extra["postprocessing"] = postprocessing_report(patches, split, val_scores, test_scores, 3)
    result = report(name, config, patches, split, val_scores, test_scores, 3, extra)
    save_run(result, test_scores, patches, split, val_scores)
    test = result["test"]
    print(
        f"{name}: веса {best['weights']} · val F1 {result['val']['f1']:.3f} · test F1 "
        f"{test['f1']:.3f} IoU {test['iou']:.3f}"
    )


def _detector_calibrate(args: argparse.Namespace) -> None:
    from littora_ml.detector.calibration import run_calibration
    from littora_ml.detector.dataset import load_patch_set

    patches = load_patch_set(resolve(DATA_VARIANTS[args.data]))
    split = _detector_split(patches, args.split)
    report = run_calibration(args.run, patches, split, args.data, args.split)
    for name, mode in report["modes"].items():
        chosen = mode["selection"]["chosen"]
        thresholds = mode["threshold"]
        params = mode["calibrators"][chosen]
        detail = f"T {params['temperature']:.3f}" if "temperature" in params else "изотоника"
        print(f"{name}: калибратор {chosen} ({detail})")
        for part in ("val", "test"):
            before = mode["reliability"][part]["raw"]
            after = mode["reliability"][part][chosen]
            print(
                f"  {part}: ECE {before['ece']:.5f} -> {after['ece']:.5f} · Brier "
                f"{before['brier']:.6f} -> {after['brier']:.6f} · log-loss "
                f"{before['log_loss']:.5f} -> {after['log_loss']:.5f}"
            )
        print(
            f"  порог val max F1 {thresholds['raw_val_max_f1']:.4f} -> калибр. "
            f"{thresholds['calibrated_val_max_f1']:.4f}, порог сервиса "
            f"{thresholds['service_raw']:.4f} -> {thresholds['service_calibrated']:.4f}"
        )
        for option, block in mode["metrics"].items():
            test = block["test"]["service"]
            print(
                f"  {option} ({block['raw_threshold']:.4f}) test сервис P {test['precision']:.3f} "
                f"R {test['recall']:.3f} F1 {test['f1']:.3f} IoU {test['iou']:.3f}"
            )


def _detector_vessels(args: argparse.Namespace) -> None:
    from littora_ml.detector.dataset import load_patch_set
    from littora_ml.detector.vessels import run_vessels

    patches = load_patch_set(resolve(DATA_VARIANTS[args.data]))
    split = _detector_split(patches, args.split)
    report = run_vessels(args.run, patches, split, args.data, args.split, zones=not args.no_zones)
    rule = report["rule"]
    print(
        f"правило: B11 >= {rule['swir_peak']:.4f} или контраст >= {rule['visible_contrast']:.4f}; "
        f"след >= {rule['trail_pixels']:.0f} пикс. при контрасте {rule['trail_contrast']:.4f}"
    )
    for part in ("fit", "test"):
        for name, block in report[part]["rates"].items():
            print(f"  {part} {name}: {block['flagged']}/{block['objects']} ({block['share']:.3f})")
    for name, block in (report["test"].get("service_zones") or {}).items():
        share = "—" if block["share"] is None else f"{block['share']:.3f}"
        print(f"  зоны сервиса test, {name}: {block['flagged']}/{block['objects']} ({share})")


def _detector_stability(args: argparse.Namespace) -> None:
    from littora_ml.detector.dataset import load_patch_set
    from littora_ml.detector.stability import run_stability

    patches = load_patch_set(resolve(DATA_VARIANTS[args.data]))
    split = _detector_split(patches, args.split)
    report = run_stability(args.run, patches, split, args.data, args.split)
    rule = report["rule"]
    print(f"порог согласия {rule['cutoff']:.3f}, флаг в сервисе: {'да' if rule['flag'] else 'нет'}")
    for part in ("fit", "test"):
        block = report[part]
        print(
            f"  {block['part']}: зоны {block['zones']}; AUC согласия {block['agreement_auc']}, "
            f"ДИ {block['agreement_auc_ci95']}; AUC вероятности {block['probability_auc']}; "
            f"внутри групп {block['agreement_auc_within_probability']}, "
            f"ДИ {block['agreement_auc_within_probability_ci95']}"
        )
        for name, share in block["flag_shares"].items():
            print(f"    флаг {name}: {share['flagged']}/{share['zones']}")


def _detector_c1check(args: argparse.Namespace) -> None:
    from littora_ml.detector.c1_check import run_c1_check
    from littora_ml.detector.dataset import load_patch_set
    from littora_ml.detector.splits import official

    c1 = load_patch_set(resolve(DATA_VARIANTS["marida_c1"]))
    l2a = load_patch_set(resolve(DATA_VARIANTS["marida_l2a"]))
    candidates = [name for name in (args.candidates or "").split(",") if name]
    report = run_c1_check(args.service, candidates, c1, l2a, official(c1.table))
    alignment = report["alignment"]
    print(
        f"совмещение: точно {alignment['scenes_aligned']}, с допуском "
        f"{alignment['scenes_tolerant']} из {alignment['scenes_with_data']} сцен; субпикс. сдвиг "
        f"медиана {alignment['subpixel_shift_median_px']}"
    )
    for name, block in report["runs"].items():
        for part in ("val", "test"):
            for mode in ("tolerant", "strict"):
                item = block[part][mode]
                if "c1" not in item:
                    print(f"{name} {part} {mode}: патчей нет")
                    continue
                print(
                    f"{name} {part} {mode} ({item['patches']} патчей, {item['scenes']} сцен): "
                    f"C1 F1 {item['c1']['f1']:.3f} {item['c1_f1_ci95']}, L2A F1 "
                    f"{item['l2a']['f1']:.3f}, разница {item['c1_minus_l2a_f1']:+.3f} "
                    f"{item['c1_minus_l2a_f1_ci95']}, вместе {item['pooled']['f1']:.3f}"
                )
    print(f"выбрано: {report['chosen']}")


def _detector_reference(args: argparse.Namespace) -> None:
    from littora_ml.detector.dataset import load_patch_set
    from littora_ml.detector.rescore import write_reference

    patches = load_patch_set(resolve(DATA_VARIANTS["marida_l2a"]))
    summary = write_reference(patches, _detector_split(patches, "common"))
    for part, block in summary.items():
        print(
            f"{part}: патчей {block['patches']}, размеченных пикселей {block['labeled_pixels']}, "
            f"мусора {block['debris_pixels']}"
        )


def _detector_rescore(args: argparse.Namespace) -> None:
    from littora_ml.detector.rescore import rescore, rescore_by_region

    for run in args.runs.split(","):
        if args.by_region:
            report = rescore_by_region(run)
            print(f"{run}: test по регионам")
            print(
                f"{'регион':<18}{'сцен':>6}{'патчей':>8}{'мусора':>9}{'TP':>8}{'FP':>8}{'FN':>8}"
                f"{'P':>8}{'R':>8}{'F1':>8}{'IoU':>8}"
            )
            for region, row in [*report["regions"].items(), ("все", report["pooled"])]:
                print(
                    f"{region:<18}{row['scenes']:>6}{row['patches']:>8}{row['debris_pixels']:>9}"
                    f"{row['tp']:>8}{row['fp']:>8}{row['fn']:>8}{row['precision']:>8.4f}"
                    f"{row['recall']:>8.4f}{row['f1']:>8.4f}{row['iou']:>8.4f}"
                )
            continue
        result = rescore(run)
        again, stored = result["recomputed"], result["stored"]
        print(
            f"{run}: {result['patches']} патчей test · пересчёт P {again['precision']:.4f} "
            f"R {again['recall']:.4f} F1 {again['f1']:.4f} IoU {again['iou']:.4f} · в отчёте "
            f"F1 {stored['f1']:.4f} IoU {stored['iou']:.4f}"
        )


def _detector_negatives(args: argparse.Namespace) -> None:
    from littora_ml.detector.regional import negatives_report

    result = negatives_report(args.run, resolve(args.labels))
    for name, row in result["by_class"].items():
        print(
            f"{name}: полигонов {row['polygons']}, пикселей {row['pixels']}, срабатываний "
            f"{row['alarm_pixels']} ({row['alarm_share']:.4%}), полигонов со срабатыванием "
            f"{row['polygons_with_alarm']}"
        )


def _detector_external(args: argparse.Namespace) -> None:
    from littora_ml.detector.external import run_plp

    collections = [name for name in (args.collections or "").split(",") if name]
    result = run_plp(args.config, resolve(args.model), collections or None)
    blocks = [result["summary"]]
    blocks.extend(variant["summary"] for variant in result["comparison"].values())
    for summary in blocks:
        print(
            f"PLP, {summary['variant']} ({' → '.join(summary['collections'])}; baseline "
            f"{', '.join(sorted(map(str, summary['baselines_used'])))}): мишеней "
            f"{summary['targets']}, пригодных {summary['usable']}"
        )
        for key, label in (
            ("plastic", "пластик"),
            ("mixed", "пластик+природное"),
            ("natural_controls", "природный контроль"),
            ("plastic_or_mixed_clean_ring", "с пластиком, чистое кольцо"),
            ("natural_controls_clean_ring", "контроль, чистое кольцо"),
        ):
            row = summary[key]
            print(
                f"  {label:<22} {row['detected']}/{row['targets']} выше порога, зоной "
                f"{row['zone_detected']} · медиана max p {row['median_max_probability'] or 0:.3f}"
            )
        for name, row in summary["by_material"].items():
            print(
                f"  {name:<22} {row['detected']}/{row['targets']} · медиана max p "
                f"{row['median_max_probability']:.3f}"
            )
        background = summary["background"]
        print(
            f"  фон: {background['alarm_pixels']} пикс. выше порога на "
            f"{background['ring_km2']:.1f} км² воды ({background['alarms_per_km2']:.2f} на км²); "
            f"во всём окне {background['window_alarm_clusters']} кластеров, "
            f"{background['window_zones']} зон сервиса на {background['window_water_km2']:.0f} км²"
        )
    wood = result["summary"]["wood_2021"]
    print(
        f"  деревянная мишень 2021: найдена {wood['located']}/{wood['expected_dates']}, "
        f"вне периода {wood['found_outside_period']}"
    )
    for day, check in result["alignment"].items():
        print(
            f"  привязка {day} {check['scene_id']}: corr0 {check['corr0']:.3f}, сдвиг "
            f"{check['best_shift']}, дробный {check['subpixel_shift']} "
            f"(corr {check['corr_subpixel']:.3f})"
        )
    for zone in result["zones"]:
        print(
            f"  {zone['zone_id']:<22} {zone.get('scene_id')} · кластеров выше порога "
            f"{zone.get('alarm_components_offshore')}, зон {zone.get('zones_offshore')} · облака "
            f"{zone.get('cloud_share') or 0:.2f}"
        )
    print(f"  {result['figure']}")


def _drift_check(args: argparse.Namespace) -> None:
    from littora_ml.drift_check.pipeline import check

    if args.stage in ("simulate", "all") and args.budget is None:
        raise SystemExit(
            "drift check --stage simulate тратит квоту Open-Meteo, общую с сервисом: "
            "задайте --budget явно"
        )
    outcome = check(load_config(args.config), args.stage, args.budget)
    if args.stage == "spread":
        for name, row in outcome["census"].items():
            print(
                f"  {name:<9} окон {row['queued']:<4} посчитано {row['used']:<4} "
                f"без кэша {row['skipped_not_cached']}"
            )
        for line in outcome["verdict"]:
            print(line)
        print(outcome["report"])
        if outcome["figure"]:
            print(outcome["figure"])
        return
    for source, row in outcome["census"].items():
        print(f"  {source:<10} дрифтеров {row['drifters']:<4} окон {row['windows']}")
    if "run" in outcome:
        run = outcome["run"]
        print(
            f"прогон: новых окон {run['new']}, из кэша {run['cached']}, ошибок форсинга "
            f"{run['forcing_errors']}, вызовов Open-Meteo {run['calls']}"
            + (f" · остановлен: {run['stopped']}" if run["stopped"] else "")
        )
    plan = outcome["plan"]
    print(
        f"осталось окон {plan['pending']} из {plan['queued']}, это до "
        f"{plan['upper_bound_calls']['total']} вызовов Open-Meteo"
    )
    for line in outcome.get("verdict", []):
        print(f"  {line}")
    if "report" in outcome:
        print(outcome["report"])
        for path in outcome["figures"]:
            print(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m littora_ml")
    commands = parser.add_subparsers(dest="command", required=True)
    audit = commands.add_parser("audit", help="аудит данных кейса и проверка утечек")
    audit.set_defaults(handler=_audit)
    detector = commands.add_parser("detector", help="детектор: данные, обучение, оценка")
    detector_commands = detector.add_subparsers(dest="action", required=True)
    prepare = detector_commands.add_parser("prepare", help="кэш патчей MARIDA и L2A")
    prepare.add_argument("--config", default="configs/detector/data.toml")
    prepare.add_argument(
        "--variant",
        choices=["marida", "l2a", "c1", "review", "mixed", "mixed_c1", "all"],
        default="all",
    )
    prepare.set_defaults(handler=_detector_prepare)
    baseline = detector_commands.add_parser("baseline", help="FDI-порог и попиксельные модели")
    baseline.add_argument("--config", required=True)
    baseline.add_argument("--data", choices=sorted(DATA_VARIANTS))
    baseline.add_argument("--split")
    baseline.set_defaults(handler=_detector_baseline)
    train = detector_commands.add_parser("train", help="обучение сегментационной сети")
    train.add_argument("--config", required=True)
    train.add_argument("--data", choices=sorted(DATA_VARIANTS))
    train.add_argument("--split")
    train.add_argument("--epochs", type=int)
    train.add_argument("--name")
    train.set_defaults(handler=_detector_train)
    evaluate = detector_commands.add_parser(
        "evaluate", help="оценка обученной модели на других данных"
    )
    source = evaluate.add_mutually_exclusive_group(required=True)
    source.add_argument("--run")
    source.add_argument("--onnx", help="внешняя модель с контрактом сервиса")
    evaluate.add_argument("--name")
    evaluate.add_argument("--data", choices=sorted(DATA_VARIANTS), required=True)
    evaluate.add_argument("--split", default="common")
    evaluate.set_defaults(handler=_detector_evaluate)
    regions = detector_commands.add_parser("regions", help="проверка на отложенных регионах")
    regions.add_argument("--config", required=True)
    regions.add_argument("--data", choices=sorted(DATA_VARIANTS))
    regions.add_argument("--jobs", type=int)
    regions.set_defaults(handler=_detector_regions)
    ensemble = detector_commands.add_parser("ensemble", help="взвешенное среднее вероятностей")
    ensemble.add_argument("--runs", required=True)
    ensemble.add_argument("--data", choices=sorted(DATA_VARIANTS), default="marida_l2a")
    ensemble.add_argument("--split", default="common")
    ensemble.set_defaults(handler=_detector_ensemble)
    predict = detector_commands.add_parser("predict", help="вероятность и зоны по сцене")
    predict.add_argument("--run", required=True)
    predict.add_argument("--scene", required=True)
    predict.add_argument("--collection", default="sentinel-2-c1-l2a")
    predict.add_argument("--bbox", required=True, help="запад,юг,восток,север")
    predict.set_defaults(handler=_detector_predict)
    summary = detector_commands.add_parser("report", help="сводка метрик и примеры")
    summary.add_argument("--figures", nargs="*", help="прогон:данные:разбиение")
    summary.set_defaults(handler=_detector_report)
    export = detector_commands.add_parser("export", help="модель для сервиса в ONNX")
    export.add_argument("--run", required=True)
    export.add_argument("--max-pixels", type=int, default=12_000_000)
    export.set_defaults(handler=_detector_export)
    calibrate = detector_commands.add_parser(
        "calibrate", help="калибровка вероятности и метрики сервиса без TTA"
    )
    calibrate.add_argument("--run", required=True)
    calibrate.add_argument("--data", choices=sorted(DATA_VARIANTS), default="marida_l2a")
    calibrate.add_argument("--split", default="common")
    calibrate.set_defaults(handler=_detector_calibrate)
    vessels = detector_commands.add_parser(
        "vessels", help="правило «вероятно судно» по разметке MARIDA train+val"
    )
    vessels.add_argument("--run", required=True)
    vessels.add_argument("--data", choices=sorted(DATA_VARIANTS), default="marida_l2a")
    vessels.add_argument("--split", default="common")
    vessels.add_argument("--no-zones", action="store_true")
    vessels.set_defaults(handler=_detector_vessels)
    c1check = detector_commands.add_parser(
        "c1check", help="сервисный режим на тех же патчах в L2A и C1"
    )
    c1check.add_argument("--service", required=True)
    c1check.add_argument("--candidates", default="")
    c1check.set_defaults(handler=_detector_c1check)
    reference = detector_commands.add_parser(
        "reference", help="эталонная разметка val и test в reports/predictions/detector/reference"
    )
    reference.set_defaults(handler=_detector_reference)
    rescore = detector_commands.add_parser(
        "rescore", help="пересчёт P, R, F1, IoU по сохранённым предсказаниям и эталону"
    )
    rescore.add_argument("--runs", required=True)
    rescore.add_argument("--by-region", action="store_true")
    rescore.set_defaults(handler=_detector_rescore)
    stability = detector_commands.add_parser(
        "stability", help="согласие зон сервиса по 8 поворотам и отражениям"
    )
    stability.add_argument("--run", required=True)
    stability.add_argument("--data", choices=sorted(DATA_VARIANTS), default="marida_l2a")
    stability.add_argument("--split", default="common")
    stability.set_defaults(handler=_detector_stability)
    negatives = detector_commands.add_parser(
        "negatives", help="срабатывания на размеченном фоне без мусора (Чёрное море)"
    )
    negatives.add_argument("--run", required=True)
    negatives.add_argument("--labels", default="data/validation/black_sea_negatives.geojson")
    negatives.set_defaults(handler=_detector_negatives)
    external = detector_commands.add_parser(
        "external", help="внешняя проверка сервисной модели на мишенях PLP"
    )
    external.add_argument("--source", choices=["plp"], required=True)
    external.add_argument("--config", default="configs/detector/data.toml")
    external.add_argument("--model", default="models/detector/service")
    external.add_argument(
        "--collections",
        help="порядок коллекций через запятую; по умолчанию как в сервисе (case.toml)",
    )
    external.set_defaults(handler=_detector_external)
    splits = commands.add_parser("splits", help="выгрузить разбиения в reports/splits")
    splits.set_defaults(handler=_splits)
    concentration = commands.add_parser("concentration", help="модель концентрации, шт./км²")
    concentration_commands = concentration.add_subparsers(dest="action", required=True)
    run = concentration_commands.add_parser("run", help="признаки, валидация, модели")
    run.add_argument("--config", default="configs/concentration/broad.toml")
    run.add_argument("--refresh", action="store_true")
    run.add_argument("--jobs", type=int, help="число параллельных процессов")
    run.set_defaults(handler=_concentration_run)
    satellite = concentration_commands.add_parser(
        "satellite", help="связь снимка и концентрации на парах S4"
    )
    satellite.add_argument("--run", help="детектор для вероятности в полосе")
    satellite.set_defaults(handler=_concentration_satellite)
    export = concentration_commands.add_parser("export", help="модели для сервиса в JSON")
    export.add_argument("--config", default="configs/concentration/broad.toml")
    export.set_defaults(handler=_concentration_export)
    outside = concentration_commands.add_parser(
        "external", help="внешняя проверка S4: Бургас (SEANOE), DOORS, EMBLAS 2016"
    )
    outside.add_argument("--config", default="configs/concentration/external.toml")
    outside.add_argument("--refresh", action="store_true")
    outside.add_argument("--jobs", type=int, help="число параллельных процессов")
    outside.add_argument("--bootstrap", type=int, help="число выборок бутстрэпа")
    outside.set_defaults(handler=_concentration_external)
    drift = commands.add_parser("drift", help="сценарий дрейфа: сверка с дрифтерами")
    drift_commands = drift.add_subparsers(dest="action", required=True)
    drift_check = drift_commands.add_parser(
        "check", help="окна по дрифтерам, прогон модели сервиса, метрики и отчёт"
    )
    drift_check.add_argument("--config", default="configs/drift/check.toml")
    drift_check.add_argument(
        "--stage", choices=["plan", "simulate", "report", "spread", "all"], default="report"
    )
    drift_check.add_argument(
        "--budget", type=float, help="предел вызовов Open-Meteo, обязателен для simulate и all"
    )
    drift_check.set_defaults(handler=_drift_check)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.handler(args)
