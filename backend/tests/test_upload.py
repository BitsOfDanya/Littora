import numpy as np
import pytest
from affine import Affine
from rasterio.io import MemoryFile

from app.analysis.upload import UploadError, read_upload
from app.earth.raster import encode_png
from tests.fakes import FakeCatalog
from tests.test_analyses import build_client
from tests.test_detector import fake_detector

CRS = "EPSG:32637"
TRANSFORM = Affine(10, 0, 400000, 0, -10, 4950000)


def geotiff(values: np.ndarray, dtype: str = "float32") -> bytes:
    profile = {
        "driver": "GTiff",
        "width": values.shape[2],
        "height": values.shape[1],
        "count": values.shape[0],
        "dtype": dtype,
        "crs": CRS,
        "transform": TRANSFORM,
    }
    with MemoryFile() as memory:
        with memory.open(**profile) as dataset:
            dataset.write(values.astype(dtype))
        return memory.read()


def sea(bands: int = 11) -> np.ndarray:
    values = np.full((bands, 120, 120), 0.02, dtype=np.float32)
    values[2] = 0.05
    values[7] = 0.01
    values[7, 40:44, 60:63] = 0.08
    return values


def test_eleven_band_reflectance_becomes_a_stack_with_a_water_mask() -> None:
    upload = read_upload(geotiff(sea()), 10_000_000)
    assert upload.stack is not None
    assert upload.stack.image.shape == (11, 120, 120)
    assert (upload.scl == 6).mean() > 0.99
    assert upload.bands == 11


def test_digital_numbers_with_the_l2a_offset_are_rescaled() -> None:
    raw = sea(12) * 10000 + 1000
    upload = read_upload(geotiff(raw, "uint16"), 10_000_000)
    assert upload.stack is not None
    assert upload.stack.image[1, 0, 0] == pytest.approx(0.02, abs=1e-3)
    assert any("10 000" in note for note in upload.notes)
    assert any("смещение" in note for note in upload.notes)


def test_declared_scale_and_offset_win_over_the_guess() -> None:
    raw = sea(11) * 0 + 1200
    content = geotiff(raw, "uint16")
    with MemoryFile(content) as memory, memory.open() as dataset:
        profile = dataset.profile
        values = dataset.read()
    with MemoryFile() as memory:
        with memory.open(**profile) as dataset:
            dataset.write(values)
            dataset.scales = [0.0001] * 11
            dataset.offsets = [0.0] * 11
        tagged = memory.read()
    upload = read_upload(tagged, 10_000_000)
    assert upload.stack is not None
    assert upload.stack.image[1, 0, 0] == pytest.approx(0.12, abs=1e-4)
    assert any("метаданных" in note for note in upload.notes)


def test_zone_area_follows_the_pixel_size() -> None:
    from app.analysis.zones import mask_zones

    mask = np.zeros((10, 10), dtype=bool)
    mask[2:4, 2:4] = True
    found: dict[str, int] = {}
    zones = mask_zones(
        mask, mask.astype(float), Affine(20, 0, 400000, 0, -20, 4950000), CRS, stats=found
    )
    assert zones[0]["area_km2"] == pytest.approx(4 * 400 / 1e6)
    assert found["total"] == 1


def test_png_without_georeference_needs_the_map_view() -> None:
    rgb = np.full((50, 60, 3), 40, dtype=np.uint8)
    with pytest.raises(UploadError):
        read_upload(encode_png(rgb), 10_000_000)
    upload = read_upload(encode_png(rgb), 10_000_000, (37.7, 44.6, 37.8, 44.7))
    assert upload.stack is None
    assert any("11 каналов" in note for note in upload.notes)


def test_uploaded_geotiff_goes_through_the_detector(tmp_path) -> None:
    with build_client(tmp_path, FakeCatalog([]), detector=fake_detector()) as client:
        response = client.post("/api/v1/uploads?name=patch.tif", content=geotiff(sea()))
        assert response.status_code == 201
        body = response.json()
        assert body["status"]["status"] == "detected"
        assert body["upload"]["kind"] == "sentinel2"
        assert {"image", "mask", "probability", "false_color"} <= set(body["layers"])
        assert client.get(f"/api/v1/analyses/{body['id']}").status_code == 200
        assert client.get(f"/api/v1/analyses/{body['id']}/export.csv").status_code == 200


def test_uploaded_photo_shows_bright_spots_without_claiming_debris(tmp_path) -> None:
    rgb = np.full((80, 80, 3), 30, dtype=np.uint8)
    rgb[40:42, 40:42] = 220
    with build_client(tmp_path, FakeCatalog([]), detector=fake_detector()) as client:
        response = client.post(
            "/api/v1/uploads?name=photo.png&bbox=37.7,44.6,37.8,44.7", content=encode_png(rgb)
        )
        body = response.json()
        assert body["status"]["status"] == "insufficient_data"
        assert body["upload"]["kind"] == "visible"
        assert len(body["upload"]["anomalies"]) == 1
        assert "anomalies" in body["layers"]
        assert body["detection"]["zones"] == []


def test_broken_file_is_a_clear_error(tmp_path) -> None:
    with build_client(tmp_path, FakeCatalog([])) as client:
        response = client.post("/api/v1/uploads?name=x.tif", content=b"not an image")
        assert response.status_code == 400
        assert "не читается" in response.json()["error"]["message"]


def test_uploaded_result_is_current_until_the_models_change(tmp_path) -> None:
    with build_client(tmp_path, FakeCatalog([]), detector=fake_detector()) as client:
        body = client.post("/api/v1/uploads?name=patch.tif", content=geotiff(sea())).json()
        assert client.get(f"/api/v1/analyses/{body['id']}").json()["stale"] is False
