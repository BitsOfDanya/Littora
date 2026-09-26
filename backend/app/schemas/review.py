from pydantic import BaseModel, Field, field_validator

from app.review.labels import ReviewLabel

COMMENT_MAX = 200
REVIEWER_MAX = 40


def _clean(value: object) -> object:
    if not isinstance(value, str):
        return value
    text = " ".join(value.split())
    return text or None


class ReviewCreate(BaseModel):
    label: ReviewLabel
    confidence: int = Field(default=2, ge=1, le=3)
    comment: str | None = Field(default=None, max_length=COMMENT_MAX)
    reviewer: str | None = Field(default=None, max_length=REVIEWER_MAX)

    @field_validator("comment", "reviewer", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> object:
        return _clean(value)
