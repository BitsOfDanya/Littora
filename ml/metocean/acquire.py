"""Reproducible environmental joins; raw responses cached by full request."""

import concurrent.futures
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import xarray as xr

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/external/metocean"
OUT = ROOT / "reports/metocean/tables"
DATA = ROOT / "data/processed/metocean"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def distance(lat, lon, lat2, lon2):
    a, b = np.radians(lat), np.radians(lat2)
    h = (
        np.sin((b - a) / 2) ** 2
        + np.cos(a) * np.cos(b) * np.sin(np.radians(lon2 - lon) / 2) ** 2
    )
    return 6371.0088 * 2 * np.arcsin(np.sqrt(np.clip(h, 0, 1)))


def prepare():
    p = pd.read_csv(ROOT / "reports/l2a_adaptation/tables/selected_patches.csv")
    matches = pd.read_csv(
        ROOT / "reports/l2a_adaptation/tables/scene_search.csv"
    ).set_index("scene_id")
    rows = []
    for r in p.itertuples():
        stac = json.loads(
            (
                ROOT / f"data/external/l2a-adaptation/stac/scene-{r.scene_id}.json"
            ).read_text()
        )
        matched = [
            f for f in stac["features"] if f["id"] == matches.loc[r.scene_id, "stac_id"]
        ]
        assert len(matched) == 1
        dt = matched[0]["properties"]["datetime"]
        rows.append(
            {
                "join_id": "patch:" + r.patch_id,
                "kind": "patch",
                "source": "MARIDA_L2A",
                "latitude": r.latitude,
                "longitude": r.longitude,
                "date": r.date,
                "observed_at": dt,
                "time_precision": "acquisition",
                "split": r.split,
                "group": r.group,
                "selection_index": r.selection_index,
            }
        )
    case = pd.read_csv(ROOT / "data/case/macroplastic_marine_samples.csv")
    for eid, g in case.groupby("event_id", sort=False):
        density = g[g.record_type == "transect_density"]
        r = (density if len(density) else g).iloc[0]
        # Source start is an interval anchor, not an invented event midpoint.
        dt = r.datetime_start_iso if pd.notna(r.time_start_utc) else ""
        if pd.notna(r.time_start_utc) and pd.isna(dt):
            dt = str(r.date_utc) + "T" + str(r.time_start_utc) + "Z"
        rows.append(
            {
                "join_id": eid,
                "kind": "field",
                "source": r.source_id,
                "latitude": r.latitude,
                "longitude": r.longitude,
                "date": r.date_utc,
                "observed_at": dt,
                "time_precision": "start_utc" if dt else "date_only",
                "split": "field_cv",
                "group": "",
                "selection_index": -1,
            }
        )
    points = pd.DataFrame(rows)
    assert points.join_id.is_unique and len(points) == 508
    assert points[["latitude", "longitude"]].notna().all().all()
    points.to_csv(DATA / "points.csv", index=False)
    print("Prepared", len(points), "points", flush=True)


def request_spec(r, product):
    date = pd.Timestamp(r.date)
    start = (date - pd.Timedelta(days=3)).strftime("%Y-%m-%d")
    base = {
        "latitude": r.latitude,
        "longitude": r.longitude,
        "start_date": start,
        "end_date": r.date,
        "timezone": "UTC",
    }
    if product == "wind":
        return (
            "https://archive-api.open-meteo.com/v1/archive",
            dict(
                base,
                hourly="wind_speed_10m,wind_direction_10m",
                models="era5",
                wind_speed_unit="ms",
                cell_selection="nearest",
            ),
            "json",
        )
    if product == "wave":
        return (
            "https://marine-api.open-meteo.com/v1/marine",
            dict(
                base,
                hourly="wave_height,wave_direction,wave_period",
                models="era5_ocean",
                cell_selection="sea",
            ),
            "json",
        )
    if r.source == "S4_BLACK_SEA_DOORS3":
        return (
            "https://marine-api.open-meteo.com/v1/marine",
            dict(
                base,
                hourly="ocean_current_velocity,ocean_current_direction",
                models="meteofrance_currents",
                velocity_unit="ms",
                cell_selection="sea",
            ),
            "json",
        )
    if date >= pd.Timestamp("2018-12-07"):
        dataset = f"GLBy0.08/expt_93.0/uv3z/{date.year}"
    elif date >= pd.Timestamp("2018-01-01"):
        dataset = "GLBv0.08/expt_93.0/uv3z"
    elif date >= pd.Timestamp("2016-05-01"):
        dataset = "GLBv0.08/expt_57.2"
    elif date >= pd.Timestamp("2016-01-01"):
        dataset = "GLBv0.08/expt_56.3"
    else:
        dataset = f"GLBv0.08/expt_53.X/data/{date.year}"
    params = {
        "var": ["water_u", "water_v"],
        "north": r.latitude + 0.081,
        "south": r.latitude - 0.081,
        "west": r.longitude - 0.081,
        "east": r.longitude + 0.081,
        "time_start": start + "T00:00:00Z",
        "time_end": r.date + "T23:59:59Z",
        "vertCoord": 0,
        "accept": "netcdf",
        "disableProjSubset": "on",
    }
    return "https://ncss.hycom.org/thredds/ncss/" + dataset, params, "nc"


def fetch(task):
    r, product = task
    url, params, ext = request_spec(r, product)
    key = hashlib.sha256(
        json.dumps([url, params], sort_keys=True).encode()
    ).hexdigest()[:24]
    path = RAW / f"{product}_{key}.{ext}"
    meta = path.with_suffix(".meta.json")
    status = {
        "join_id": r.join_id,
        "product": product,
        "path": str(path.relative_to(ROOT)),
        "url": requests.Request("GET", url, params=params).prepare().url,
    }
    if path.exists() and meta.exists():
        return dict(status, **json.loads(meta.read_text()))
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, timeout=(15, 90))
            if resp.status_code == 429:
                time.sleep(20 * (attempt + 1))
            resp.raise_for_status()
            if ext == "json":
                obj = resp.json()
                assert "hourly" in obj, str(obj)[:200]
            else:
                assert resp.content[:3] == b"CDF" or resp.content[:4] == b"\x89HDF", (
                    resp.text[:120]
                )
            path.write_bytes(resp.content)
            details = {
                "status": "ok",
                "sha256": sha(path),
                "bytes": len(resp.content),
                "retrieved_at": pd.Timestamp.now(tz="UTC").isoformat(),
            }
            meta.write_text(json.dumps(details, indent=2))
            return dict(status, **details)
        except (requests.RequestException, ValueError, AssertionError, OSError) as e:
            error = repr(e)[:350]
            if attempt < 2:
                time.sleep(2 + attempt * 3)
    return dict(status, status="error", error=error)


def download():
    p = pd.read_csv(DATA / "points.csv").fillna("")
    tasks = [
        (r, product) for r in p.itertuples() for product in ["wind", "wave", "current"]
    ]
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for i, result in enumerate(pool.map(fetch, tasks)):
            rows.append(result)
            if i % 30 == 0:
                pd.DataFrame(rows).to_csv(OUT / "download_manifest.csv", index=False)
                print(
                    i + 1,
                    "/",
                    len(tasks),
                    "errors",
                    sum(x["status"] != "ok" for x in rows),
                    flush=True,
                )
    pd.DataFrame(rows).to_csv(OUT / "download_manifest.csv", index=False)


def parse_series(path, r, product):
    if path.suffix == ".json":
        obj = json.loads(path.read_text())
        h = pd.DataFrame(obj["hourly"])
        h["time"] = pd.to_datetime(h.time, utc=True)
        units = obj["hourly_units"]
        dist = float(
            distance(r.latitude, r.longitude, obj["latitude"], obj["longitude"])
        )
        if product == "wind":
            assert units["wind_speed_10m"] == "m/s"
            a = np.radians(h.wind_direction_10m.astype(float))
            s = h.wind_speed_10m.astype(float)
            vals = {
                "wind_speed_ms": s,
                "wind_u_ms": -s * np.sin(a),
                "wind_v_ms": -s * np.cos(a),
            }
        elif product == "wave":
            assert units["wave_height"] == "m" and units["wave_period"] == "s"
            a = np.radians(h.wave_direction.astype(float))
            vals = {
                "wave_height_m": h.wave_height.astype(float),
                "wave_period_s": h.wave_period.astype(float),
                "wave_from_sin": np.sin(a),
                "wave_from_cos": np.cos(a),
            }
        else:
            # Open-Meteo current direction is the direction TO which water flows.
            s = h.ocean_current_velocity.astype(float)
            unit = units["ocean_current_velocity"]
            assert unit in ["m/s", "km/h"]
            if unit == "km/h":
                s = s / 3.6
            a = np.radians(h.ocean_current_direction.astype(float))
            vals = {
                "current_speed_ms": s,
                "current_u_ms": s * np.sin(a),
                "current_v_ms": s * np.cos(a),
            }
        frame = pd.DataFrame(vals)
        frame.index = pd.DatetimeIndex(h.time)
        return (
            frame,
            {
                "grid_latitude": obj["latitude"],
                "grid_longitude": obj["longitude"],
                "grid_distance_km": dist,
                "native_step_h": 1,
            },
            40 if product == "wind" else (60 if product == "wave" else 15),
        )
    with xr.open_dataset(path) as ds:
        assert float(ds.depth.values.flat[0]) == 0
        u = ds.water_u.isel(depth=0).load()
        v = ds.water_v.isel(depth=0).load()
        assert ds.water_u.attrs["units"] == "m/s"
        assert "scale_factor" in ds.water_u.encoding, (
            "Packed current scale must be retained"
        )
        lat, lon = np.meshgrid(ds.lat.values, ds.lon.values, indexing="ij")
        lon = (lon + 180) % 360 - 180
        dd = distance(r.latitude, r.longitude, lat, lon)
        valid = np.isfinite(u.values).any(axis=0) & np.isfinite(v.values).any(axis=0)
        # Selection uses physical coverage only, never litter labels.
        if valid.any():
            iy, ix = np.unravel_index(np.argmin(np.where(valid, dd, np.inf)), dd.shape)
        else:
            iy, ix = np.unravel_index(np.argmin(dd), dd.shape)
        uu = u.values[:, iy, ix]
        vv = v.values[:, iy, ix]
        frame = pd.DataFrame(
            {
                "current_u_ms": uu,
                "current_v_ms": vv,
                "current_speed_ms": np.hypot(uu, vv),
            },
            index=pd.to_datetime(ds.time.values, utc=True),
        )
        return (
            frame,
            {
                "grid_latitude": lat[iy, ix],
                "grid_longitude": lon[iy, ix],
                "grid_distance_km": float(dd[iy, ix]),
                "native_step_h": 3,
            },
            15,
        )


def summarize(frame, observed_at, date, step):
    """Use no post-observation timesteps; date-only records get daily context."""
    frame = frame.sort_index()
    out = {}
    known = bool(observed_at) and pd.notna(observed_at)
    if known:
        end = pd.Timestamp(observed_at)
        before = frame.loc[frame.index <= end]
        age = (end - before.index[-1]).total_seconds() / 3600 if len(before) else np.inf
        out["time_offset_h"] = age
        for c in frame:
            out[c + "_instant"] = (
                float(before[c].iloc[-1]) if age <= step and len(before) else np.nan
            )
        for hours in [24, 72]:
            sub = frame.loc[
                (frame.index > end - pd.Timedelta(hours=hours)) & (frame.index <= end)
            ]
            for c in frame:
                coverage = sub[c].notna().sum() / (hours / step)
                out[c + f"_mean{hours}h"] = (
                    float(sub[c].mean()) if coverage >= 0.75 else np.nan
                )
                out[c + f"_coverage{hours}h"] = min(1.0, coverage)
    else:
        day = pd.Timestamp(date, tz="UTC")
        sub = frame.loc[
            (frame.index >= day) & (frame.index < day + pd.Timedelta(days=1))
        ]
        for c in frame:
            out[c + "_daily_mean"] = (
                float(sub[c].mean())
                if sub[c].notna().sum() >= 0.75 * 24 / step
                else np.nan
            )
    return out


def extract():
    points = pd.read_csv(DATA / "points.csv").fillna("")
    manifest = pd.read_csv(OUT / "download_manifest.csv")
    features = []
    quality = []
    long = []
    for r in points.itertuples():
        row = r._asdict()
        row.pop("Index", None)
        for m in manifest[manifest.join_id == r.join_id].itertuples():
            q = {
                "join_id": r.join_id,
                "kind": r.kind,
                "source": r.source,
                "split": r.split,
                "product": m.product,
                "status": m.status,
            }
            if m.status != "ok":
                quality.append(q)
                continue
            try:
                frame, meta, limit = parse_series(ROOT / m.path, r, m.product)
                q.update(meta)
                q["values_present"] = int(frame.notna().sum().sum())
                q["time_rows"] = len(frame)
                q["status"] = "ok" if frame.notna().any().any() else "no_valid_sea_cell"
                if meta["grid_distance_km"] > limit:
                    q["status"] = "grid_too_far"
                    frame[:] = np.nan
                for c in frame:
                    if c.endswith("_ms") and not c.startswith(
                        ("wind_u", "wind_v", "current_u", "current_v")
                    ):
                        assert (frame[c].dropna() >= 0).all()
                vals = summarize(frame, r.observed_at, r.date, meta["native_step_h"])
                if "time_offset_h" in vals:
                    q["time_offset_h"] = vals.pop("time_offset_h")
                row.update(vals)
                long.append(
                    frame.reset_index(names="time").assign(
                        join_id=r.join_id, product=m.product
                    )
                )
            except (ValueError, KeyError, AssertionError, OSError, IndexError) as e:
                q.update(status="parse_error", error=str(e))
            quality.append(q)
        features.append(row)
    f = pd.DataFrame(features)
    f.to_csv(DATA / "features.csv", index=False)
    pd.DataFrame(quality).to_csv(OUT / "join_quality.csv", index=False)
    if long:
        pd.concat(long, ignore_index=True).to_csv(
            DATA / "timeseries.csv.gz", index=False
        )
    case = pd.read_csv(ROOT / "data/case/macroplastic_marine_samples.csv")
    env = f[f.kind == "field"].drop(
        columns=[
            "source",
            "latitude",
            "longitude",
            "date",
            "split",
            "group",
            "selection_index",
        ]
    )
    merged = case.merge(
        env, left_on="event_id", right_on="join_id", how="left", validate="many_to_one"
    )
    assert len(merged) == len(case)
    merged.to_csv(DATA / "macroplastic_marine_samples_metocean.csv", index=False)
    print(
        pd.DataFrame(quality).groupby(["product", "status"]).size().to_string(),
        flush=True,
    )


if __name__ == "__main__":
    for p in [RAW, OUT, DATA]:
        p.mkdir(exist_ok=True, parents=True)
    {"prepare": prepare, "download": download, "extract": extract}[sys.argv[1]]()
