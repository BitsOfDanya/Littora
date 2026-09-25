import logging

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s  %(message)s"


def configure_logging(level: str) -> None:
    logging.basicConfig(level=level, format=LOG_FORMAT, force=True)
    logging.getLogger("uvicorn.access").setLevel(max(logging.getLevelName(level), logging.INFO))
    for noisy in ("rasterio", "httpx", "httpx2"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
