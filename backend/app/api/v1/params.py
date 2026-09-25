from app.core.errors import AppError


def parse_bbox(value: str | None) -> tuple[float, float, float, float] | None:
    if value is None or not value.strip():
        return None
    try:
        west, south, east, north = (float(part) for part in value.split(","))
    except ValueError as error:
        raise AppError("bbox задаётся как «запад,юг,восток,север» в градусах") from error
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise AppError("bbox задан неверно: нужны запад < восток и юг < север")
    return west, south, east, north
