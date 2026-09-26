from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[3]
DATA = REPOSITORY / "data"
CASE_CSV = DATA / "case" / "macroplastic_marine_samples.csv"
EXTERNAL = DATA / "external"
INTERIM = DATA / "interim"
PROCESSED = DATA / "processed"
REPORTS = REPOSITORY / "reports"
MODELS = REPOSITORY / "models"
CONFIGS = REPOSITORY / "configs"
CASE_CONFIG = REPOSITORY / "backend" / "config" / "case.toml"
REGISTRY = REPORTS / "registry"


def resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else REPOSITORY / candidate
