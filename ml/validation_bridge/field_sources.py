"""Prepare DOORS source audit and optical observations without transferring station times to litter."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from imagery import quality, read_asset, search
from pyproj import Geod, Transformer
from rasterio.transform import from_origin

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/external/doors-research"
OUT = ROOT / "reports/validation_bridge/tables"
RECORDS = {
    15172377: "15172377.xlsx",
    15129753: "15129753.xlsx",
    15259958: "AOP_DOORS_cruise_3.xlsx",
    15120079: "CHL_TSM_SD_DOORS_cruise_3.xlsx",
    15778382: "15778382-DOORS_Jun2024_Rrs.csv",
    15044582: "15044582-AOT_DOORS_cruise_3.xlsx",
}


def acquire():
    RAW.mkdir(parents=True, exist_ok=True)
    manifest = []
    for rid, name in RECORDS.items():
        p = RAW / f"{rid}.json"
        if not p.exists():
            r = requests.get(f"https://zenodo.org/api/records/{rid}", timeout=30)
            r.raise_for_status()
            p.write_text(r.text)
        j = json.loads(p.read_text())
        for f in j["files"]:
            target = RAW / (
                name if not f["key"].endswith(".pdf") else f"{rid}-" + f["key"]
            )
            if not target.exists():
                r = requests.get(f["links"]["self"], timeout=60)
                r.raise_for_status()
                target.write_bytes(r.content)
            digest = hashlib.md5(target.read_bytes()).hexdigest()
            assert digest == f["checksum"].removeprefix("md5:"), (
                target,
                "checksum mismatch",
            )
            manifest.append(
                {
                    "record_id": rid,
                    "doi": j["doi"],
                    "license": j["metadata"]["license"]["id"],
                    "path": str(target.relative_to(ROOT)),
                    "url": f["links"]["self"],
                    "md5": digest,
                    "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                }
            )
    pd.DataFrame(manifest).to_csv(OUT / "source_manifest.csv", index=False)


def normalize():
    a = pd.read_excel(RAW / "15172377.xlsx")
    b = pd.read_excel(RAW / "15129753.xlsx")
    pd.testing.assert_frame_equal(a, b)
    doors = a.iloc[:, 1:].copy()
    doors.columns = [
        "transect_id",
        "date_reported",
        "latitude",
        "longitude",
        "density_items_km2",
    ]
    doors["date"] = pd.to_datetime(doors.date_reported, format="%d.%m.%Y").dt.strftime(
        "%Y-%m-%d"
    )
    doors["source_row"] = np.arange(2, len(doors) + 2)
    doors["source_doi"] = "10.5281/zenodo.15172377"
    doors["position_role"] = "published_transect_midpoint"
    doors["time_status"] = "date_only"
    for k in [
        "start_time_utc",
        "end_time_utc",
        "lat_start",
        "lon_start",
        "lat_end",
        "lon_end",
        "width_m",
        "length_m",
        "area_km2",
        "items_count",
    ]:
        doors[k] = np.nan
    doors["missing_fields"] = (
        "UTC_start_end;endpoints_or_track;strip_width;surveyed_area;item_count"
    )
    doors["precise_pairing_ready"] = False
    doors["density_available"] = True
    case = pd.read_csv(ROOT / "data/case/macroplastic_marine_samples.csv")
    c = case[case.measurement_profile == "S4_visual_GT2_5"].sort_values(
        "source_event_id"
    )
    check = doors.merge(
        c[["source_event_id", "concentration_items_km2", "latitude", "longitude"]],
        left_on="transect_id",
        right_on="source_event_id",
        suffixes=("", "_case"),
        validate="one_to_one",
    )
    assert len(check) == 33
    assert np.allclose(check.density_items_km2, check.concentration_items_km2)
    matched = np.isclose(check.latitude, check.latitude_case) & np.isclose(
        check.longitude, check.longitude_case
    )
    swapped = np.isclose(check.latitude, check.longitude_case) & np.isclose(
        check.longitude, check.latitude_case
    )
    assert (matched | swapped).all(), "Unexplained source/case coordinate difference"
    check["coordinate_status"] = np.where(
        matched, "matches_case", "source_lat_lon_swapped_in_existing_case"
    )
    check.to_csv(OUT / "doors_case_coordinate_audit.csv", index=False)
    doors["coordinate_status"] = check.coordinate_status.to_numpy()
    doors["source_coordinate_usable"] = matched
    # Preserve the raw T33 values here; the existing case has a documented correction.

    doors.to_csv(OUT / "doors_transects_pending_geometry.csv", index=False)
    optical = pd.read_csv(RAW / "15778382-DOORS_Jun2024_Rrs.csv")
    # Published headers mix Rrs_400 and Rrs850; normalize only wavelength columns.
    optical = optical.rename(
        columns={
            c: "Rrs_" + c.removeprefix("Rrs").lstrip("_")
            for c in optical
            if c.startswith("Rrs")
        }
    ).copy()
    optical["datetime_utc"] = pd.to_datetime(
        optical.Date + " " + optical["Time[UTC]"], format="%d/%m/%Y %H:%M:%S", utc=True
    )
    optical["record_id"] = [
        "DOORS3:TriOS:" + str(i) for i in range(1, len(optical) + 1)
    ]
    optical["source_doi"] = "10.5281/zenodo.15778382"
    optical["target_type"] = "optical_Rrs_sr-1"
    optical["litter_label_available"] = False
    assert optical.Units.eq("sr^-1").all()
    assert len(optical.filter(like="Rrs_").columns) == 451
    optical.to_csv(OUT / "doors_trios_rrs.csv", index=False)
    aop = pd.read_excel(RAW / "AOP_DOORS_cruise_3.xlsx", sheet_name="Sheet1 (2)")
    aop["datetime_utc"] = pd.to_datetime(
        aop.Date.dt.strftime("%Y-%m-%d")
        + " "
        + aop["Time (UTC)"].astype(str).str.strip(),
        utc=True,
    )
    aop["target_type"] = "optical_Rrs_Kd"
    aop["litter_label_available"] = False
    aop.to_csv(OUT / "doors_micropro_aop.csv", index=False)
    hydro = pd.read_excel(RAW / "CHL_TSM_SD_DOORS_cruise_3.xlsx")
    hydro["litter_label_available"] = False
    hydro.to_csv(OUT / "doors_water_quality.csv", index=False)
    geod = Geod(ellps="WGS84")
    candidates = []
    for t in doors.itertuples():
        if not t.source_coordinate_usable:
            continue
        same = optical[optical.datetime_utc.dt.strftime("%Y-%m-%d") == t.date]
        if same.empty:
            continue
        distances = [
            geod.inv(t.longitude, t.latitude, r.Longitude, r.Latitude)[2]
            for r in same.itertuples()
        ]
        best = same.iloc[int(np.argmin(distances))]
        candidates.append(
            {
                "transect_id": t.transect_id,
                "optical_record_id": best.record_id,
                "same_date": True,
                "distance_m": min(distances),
                "join_approved": False,
                "reason": "No shared survey ID or litter timestamp; spatial proximity is not identity",
            }
        )
    pd.DataFrame(candidates).to_csv(
        OUT / "doors_optical_neighbours_NOT_JOINED.csv", index=False
    )
    return doors, optical


def optical_pairs(optical):
    rows = []
    for o in optical.itertuples():
        date = o.datetime_utc.date().isoformat()
        key = "optical-" + o.record_id.replace(":", "-")
        items = search(
            [
                o.Longitude - 0.001,
                o.Latitude - 0.001,
                o.Longitude + 0.001,
                o.Latitude + 0.001,
            ],
            date,
            date,
            key,
        )
        if not items:
            rows.append(
                {
                    "record_id": o.record_id,
                    "station": o.Station,
                    "date": date,
                    "accepted": False,
                    "reason": "no_same_day_scene",
                }
            )
            continue
        epsg = 32600 + int((o.Longitude + 180) // 6) + 1
        x, y = Transformer.from_crs(4326, epsg, always_xy=True).transform(
            o.Longitude, o.Latitude
        )
        # 3x3 pixels around field location, all nine must be valid water for this pilot.
        x = np.floor(x / 10) * 10 + 5
        y = np.floor(y / 10) * 10 + 5
        profile = {
            "height": 3,
            "width": 3,
            "crs": f"EPSG:{epsg}",
            "transform": from_origin(x - 15, y + 15, 10, 10),
        }
        for item in items:
            dt = (
                abs(
                    (
                        pd.Timestamp(item["properties"]["datetime"]) - o.datetime_utc
                    ).total_seconds()
                )
                / 3600
            )
            row = {
                "record_id": o.record_id,
                "station": o.Station,
                "date": date,
                "stac_id": item["id"],
                "time_difference_hours": dt,
                "field_datetime_utc": o.datetime_utc.isoformat(),
                "satellite_datetime": item["properties"]["datetime"],
                "accepted": False,
                "reason": "time_difference_over_3h",
                "target_type": "optical_only_not_litter",
            }
            if dt <= 3:
                scl = read_asset(item, "scl", profile)
                q = quality(scl)
                row.update(q)
                row["accepted"] = q["water_fraction"] == 1 and q["nodata_fraction"] == 0
                row["reason"] = (
                    "optical_match_candidate"
                    if row["accepted"]
                    else "3x3_not_all_valid_water"
                )
            rows.append(row)
    frame = pd.DataFrame(rows)
    frame.to_csv(OUT / "doors_optical_satellite_candidates.csv", index=False)
    print(
        "Optical stations",
        len(optical),
        "candidate pairs accepted",
        int(frame.accepted.sum()),
        flush=True,
    )


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    acquire()
    _doors, optical = normalize()
    optical_pairs(optical)
    print(
        "DOORS33 equivalent across DOIs; precise litter time/area recovered: 0",
        flush=True,
    )


if __name__ == "__main__":
    main()
