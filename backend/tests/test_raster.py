import numpy as np
import pytest
from rasterio.io import MemoryFile

from app.earth.raster import encode_png


@pytest.mark.filterwarnings("ignore::rasterio.errors.NotGeoreferencedWarning")
@pytest.mark.parametrize("channels", [3, 4])
def test_png_layers_decode_losslessly(channels: int) -> None:
    rng = np.random.default_rng(7)
    pixels = rng.integers(0, 256, size=(31, 45, channels), dtype=np.uint8)
    pixels[4:20, 6:30] = 40
    with MemoryFile(encode_png(pixels)) as memory, memory.open() as dataset:
        decoded = np.moveaxis(dataset.read(), 0, -1)
    assert np.array_equal(decoded, pixels)


def test_png_encoder_rejects_other_shapes() -> None:
    with pytest.raises(ValueError):
        encode_png(np.zeros((4, 4), dtype=np.uint8))
