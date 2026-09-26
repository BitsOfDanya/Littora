"""Normalize published observations without inventing location, UTC or target units."""

import hashlib
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import xarray as xr
from pyproj import Transformer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/expansion/tables"


def normalize_emblas(path):
    source = pd.read_excel(path, sheet_name="TableS2_Monitoring sessions").iloc[
        :302, :14
    ]
    source.columns = [
        "session_id",
        "start_time_reported",
        "beaufort",
        "duration_h",
        "observer_height_m",
        "width_m",
        "length_m",
        "items_count",
        "area_km2",
        "reported_density_items_km2",
        "year",
        "basin_sector",
        "distance_to_coast_category",
        "subregion",
    ]
    assert source.session_id.is_unique and len(source) == 302
    source["event_id"] = "EMBLAS2022:" + source.session_id.astype(int).astype(str)
    source["source_row"] = np.arange(2, len(source) + 2)
    source["source_doi"] = "10.1016/j.envpol.2022.119816"
    source["source_sheet"] = "TableS2_Monitoring sessions"
    source["source_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    source["recalculated_density_items_km2"] = source.items_count / source.area_km2
    source["recalculated_area_km2"] = source.width_m * source.length_m / 1e6
    source["is_observed_zero"] = source.items_count.eq(0)
    source["target_scope"] = "all_litter"
    source["sampling_method"] = "visual"
    source["time_zone_status"] = "not_reported"
    source["latitude"] = np.nan
    source["longitude"] = np.nan
    source["coordinate_status"] = "missing_session_link"
    source["t3_eligible"] = False
    source["exclusion_reason"] = (
        "missing_verified_session_coordinates;unresolved_time_zone"
    )
    assert (source.area_km2 > 0).all() and (source.items_count >= 0).all()
    assert np.allclose(source.area_km2, source.recalculated_area_km2, atol=5e-5, rtol=0)
    assert (
        np.max(
            abs(
                source.reported_density_items_km2
                - source.recalculated_density_items_km2
            )
        )
        < 0.06
    )
    return source


def plp_observations(root):
    rows = []
    for shp in sorted(root.rglob("*.shp")):
        date = shp.parent.name
        geo = gpd.read_file(shp).to_crs(4326)
        (nc,) = root.rglob(f"*_{date}_L2W_AOI.nc")
        with xr.open_dataset(nc) as ds:
            # NetCDF publishes lon/lat per pixel; match the independently georeferenced UAV points.
            project = Transformer.from_crs(4326, 32635, always_xy=True)
            xx, yy = project.transform(ds.lon.values, ds.lat.values)
            xp, yp = project.transform(geo.geometry.x.values, geo.geometry.y.values)
            spectral = sorted(
                (k for k in ds.data_vars if k.startswith("rhos_")),
                key=lambda k: int(k.split("_")[1]),
            )
            assert len(spectral) == 11
            seen = set()
            for j, (_, point) in enumerate(geo.iterrows()):
                distance = np.hypot(xx - xp[j], yy - yp[j])
                r, c = np.unravel_index(np.nanargmin(distance), distance.shape)
                spatial_valid = distance[r, c] < 7.1
                if spatial_valid:
                    assert (r, c) not in seen, (shp, j, "duplicate pixel")
                    seen.add((r, c))
                cover = {
                    k: float(point.get(k, 0))
                    for k in ["CP_Bags", "CP_Bottles", "CP_Reeds", "CP_Sea"]
                }
                assert abs(sum(cover.values()) - 100) < 1e-6, (shp, j, cover)
                row = dict(
                    date=pd.Timestamp(date).date().isoformat(),
                    pixel_name=point.Pixel_name,
                    longitude=point.geometry.x,
                    latitude=point.geometry.y,
                    nc_row=int(r),
                    nc_col=int(c),
                    match_distance_m=float(distance[r, c]),
                    plastic_cover_pct=cover["CP_Bags"] + cover["CP_Bottles"],
                    **cover,
                    input_product="ACOLITE_rhos",
                    source_shapefile=str(shp.relative_to(ROOT)),
                    source_netcdf=str(nc.relative_to(ROOT)),
                    satellite_time=ds.attrs["isodate"],
                    l2_flags=int(ds.l2_flags.values[r, c]),
                    spatial_match_valid=spatial_valid,
                    exclusion_reason=""
                    if spatial_valid
                    else "outside_pixel_match_tolerance",
                )
                row.update(
                    {
                        f"band_{b:02d}": float(ds[k].values[r, c])
                        for b, k in enumerate(spectral)
                    }
                )
                rows.append(row)
    frame = pd.DataFrame(rows)
    assert np.isfinite(frame.filter(like="band_").to_numpy()).all()
    return frame


def plp_cross_validation(frame):
    # Fixed before seeing scores: small linear cover model, no MARIDA rhorc model on rhos data.
    frame = frame.loc[frame.spatial_match_valid].reset_index(drop=True)
    x = frame.filter(like="band_").to_numpy()
    y = frame.plastic_cover_pct.to_numpy()
    rows = []
    for train, test in LeaveOneGroupOut().split(x, y, frame.date):
        model = make_pipeline(StandardScaler(), Ridge(alpha=10.0))
        model.fit(x[train], y[train])
        for name, pred in [
            ("train_mean", np.repeat(y[train].mean(), len(test))),
            ("ridge_rhos", np.clip(model.predict(x[test]), 0, 100)),
        ]:
            rows.extend(
                {
                    "index": int(i),
                    "date": frame.iloc[i].date,
                    "pixel_name": frame.iloc[i].pixel_name,
                    "model": name,
                    "observed": float(y[i]),
                    "predicted": float(p),
                }
                for i, p in zip(test, pred)
            )
    predictions = pd.DataFrame(rows)
    metrics = []
    for name, g in predictions.groupby("model"):
        metrics.append(
            {
                "model": name,
                "pixels": len(g),
                "dates": g.date.nunique(),
                "mae_percentage_points": mean_absolute_error(g.observed, g.predicted),
                "r2": r2_score(g.observed, g.predicted),
            }
        )
    return predictions, pd.DataFrame(metrics)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    emblas = normalize_emblas(
        ROOT / "data/external/emblas-floating-litter/gonzalez-fernandez2022-mmc2.xlsx"
    )
    emblas.to_csv(OUT / "emblas_events_pending.csv", index=False)
    emblas.groupby("year").agg(
        events=("session_id", "size"),
        zeros=("is_observed_zero", "sum"),
        items=("items_count", "sum"),
        surveyed_area_km2=("area_km2", "sum"),
        median_density=("reported_density_items_km2", "median"),
    ).to_csv(OUT / "emblas_year_summary.csv")
    plp = plp_observations(ROOT / "data/external/plp2019/PLP2019_dataset")
    plp.to_csv(OUT / "plp2019_pixel_cover.csv", index=False)
    pred, metrics = plp_cross_validation(plp)
    pred.to_csv(OUT / "plp2019_date_holdout_predictions.csv", index=False)
    metrics.to_csv(OUT / "plp2019_date_holdout_metrics.csv", index=False)
    print(
        "EMBLAS",
        len(emblas),
        "zeros",
        int(emblas.is_observed_zero.sum()),
        "T3",
        int(emblas.t3_eligible.sum()),
    )
    print(
        "PLP",
        len(plp),
        "dates",
        plp.date.nunique(),
        "zero plastic",
        (plp.plastic_cover_pct == 0).sum(),
    )
    print(metrics.to_string(index=False))


if __name__ == "__main__":
    main()
