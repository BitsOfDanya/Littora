"""ERA5 context ablation on the existing field-observation CV folds."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/expansion/tables"
RAW = ROOT / "data/external/era5-openmeteo"
PROFILES = ["S3_visual_GT2", "S4_visual_GT2_5"]


def fetch(row):
    day = (pd.Timestamp(row.date_utc) - pd.Timedelta(days=1)).date().isoformat()
    params = {
        "latitude": float(row.latitude),
        "longitude": float(row.longitude),
        "start_date": day,
        "end_date": day,
        "hourly": "wind_speed_10m,wind_direction_10m,precipitation",
        "models": "era5",
        "timezone": "UTC",
        "wind_speed_unit": "ms",
        "cell_selection": "sea",
    }
    key = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()
    path = RAW / f"{key}.json"
    if path.exists():
        response = json.loads(path.read_text())
    else:
        r = requests.get(
            "https://archive-api.open-meteo.com/v1/archive", params=params, timeout=60
        )
        r.raise_for_status()
        response = r.json()
        path.write_text(json.dumps(response))
    h = response["hourly"]
    speed = np.array(h["wind_speed_10m"], dtype=float)
    direction = np.deg2rad(h["wind_direction_10m"])
    rain = np.array(h["precipitation"], dtype=float)
    assert (
        len(speed) == len(direction) == len(rain) == 24
        and np.isfinite([speed, direction, rain]).all()
    )
    assert (
        response["hourly_units"]["wind_speed_10m"] == "m/s"
        and response["utc_offset_seconds"] == 0
    )
    return {
        "event_id": row.event_id,
        "context_day_utc": day,
        "era5_grid_lat": response["latitude"],
        "era5_grid_lon": response["longitude"],
        "wind_mean_ms": float(speed.mean()),
        "wind_max_ms": float(speed.max()),
        "wind_u_mean_ms": float((-speed * np.sin(direction)).mean()),
        "wind_v_mean_ms": float((-speed * np.cos(direction)).mean()),
        "precipitation_mm": float(rain.sum()),
        "raw_file": str(path.relative_to(ROOT)),
        "request_url": requests.Request(
            "GET", "https://archive-api.open-meteo.com/v1/archive", params=params
        )
        .prepare()
        .url,
        "raw_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    members = pd.read_csv(ROOT / "reports/eda/tables/cv_memberships.csv")
    members = members[members.measurement_profile.isin(PROFILES)]
    case = pd.read_csv(ROOT / "data/case/macroplastic_marine_samples.csv")
    case = case[case.sample_id.isin(members.sample_id.unique())].copy()
    assert len(case) == 74
    print("Fetching prior-day ERA5 for", len(case), "events", flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(fetch, case.itertuples(index=False)))
    weather = pd.DataFrame(rows)
    weather.to_csv(OUT / "era5_event_context.csv", index=False)
    case = case.merge(weather, on="event_id", validate="one_to_one")
    doy = pd.to_datetime(case.date_utc).dt.dayofyear
    case["season_sin"] = np.sin(2 * np.pi * doy / 365.25)
    case["season_cos"] = np.cos(2 * np.pi * doy / 365.25)
    base = ["latitude", "longitude", "season_sin", "season_cos"]
    extra = [
        "wind_mean_ms",
        "wind_max_ms",
        "wind_u_mean_ms",
        "wind_v_mean_ms",
        "precipitation_mm",
    ]
    case = case.set_index("event_id")
    predictions = []
    for (profile, fold), g in members.groupby(["measurement_profile", "fold"]):
        train = case.loc[g.loc[g.role == "train", "event_id"]]
        test = case.loc[g.loc[g.role == "test", "event_id"]]
        assert set(g.loc[g.role == "train", "group"]).isdisjoint(
            g.loc[g.role == "test", "group"]
        )
        y = train.concentration_items_km2.to_numpy()
        groups = g[g.role == "test"].set_index("event_id").group
        for name, features in [
            ("train_median", []),
            ("location_season", base),
            ("location_season_weather", base + extra),
        ]:
            if not features:
                p = np.repeat(np.median(y), len(test))
            else:
                model = RandomForestRegressor(
                    n_estimators=125,
                    max_depth=5,
                    min_samples_leaf=3,
                    random_state=42,
                    n_jobs=4,
                )
                model.fit(train[features], np.log1p(y))
                p = np.expm1(model.predict(test[features]))
            predictions.extend(
                {
                    "profile": profile,
                    "fold": int(fold),
                    "event_id": e,
                    "group": groups[e],
                    "model": name,
                    "observed": float(t),
                    "predicted": float(v),
                }
                for e, t, v in zip(test.index, test.concentration_items_km2, p)
            )
    pred = pd.DataFrame(predictions)
    pred.to_csv(OUT / "weather_oof_predictions.csv", index=False)
    metrics = []
    for (profile, model), g in pred.groupby(["profile", "model"]):
        metrics.append(
            {
                "profile": profile,
                "model": model,
                "events": len(g),
                "mae_items_km2": mean_absolute_error(g.observed, g.predicted),
                "rmse_items_km2": np.sqrt(mean_squared_error(g.observed, g.predicted)),
                "r2": r2_score(g.observed, g.predicted),
            }
        )
    pd.DataFrame(metrics).to_csv(OUT / "weather_oof_metrics.csv", index=False)
    gains = []
    rng = np.random.default_rng(42)
    for profile, g in pred.groupby("profile"):
        g = g.copy()
        g["ae"] = abs(g.observed - g.predicted)
        wide = g.pivot(
            index=["event_id", "group"], columns="model", values="ae"
        ).reset_index()
        wide["gain"] = wide.location_season - wide.location_season_weather
        units = [v.gain.to_numpy() for _, v in wide.groupby("group")]
        vals = [
            np.concatenate(
                [units[i] for i in rng.integers(0, len(units), len(units))]
            ).mean()
            for _ in range(1000)
        ]
        gains.append(
            {
                "profile": profile,
                "mae_gain_items_km2": wide.gain.mean(),
                "low": np.quantile(vals, 0.025),
                "high": np.quantile(vals, 0.975),
                "groups": len(units),
            }
        )
    pd.DataFrame(gains).to_csv(OUT / "weather_paired_gain.csv", index=False)
    print(pd.DataFrame(metrics).to_string(index=False))
    print(pd.DataFrame(gains).to_string(index=False))


if __name__ == "__main__":
    main()
