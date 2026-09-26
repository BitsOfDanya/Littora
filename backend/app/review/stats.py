from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Iterable
from typing import Any

from app.review.labels import LABEL_TITLES, POSITIVE, UNDECIDED, ReviewLabel

Z_95 = 1.959964


def reviewer_key(reviewer: str | None) -> str:
    return (reviewer or "").strip().casefold()


def zone_key(record: dict[str, Any]) -> tuple[str, str, str]:
    anchor = record.get("analysis_id") or record.get("scene_id") or ""
    return record["source"], anchor, record["zone_id"]


def latest(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    chosen: dict[tuple, dict[str, Any]] = {}
    for record in records:
        chosen[(*zone_key(record), reviewer_key(record.get("reviewer")))] = record
    return list(chosen.values())


def consensus(reviews: list[dict[str, Any]]) -> str | None:
    if not reviews:
        return None
    weight: dict[str, tuple[int, int]] = {}
    for review in reviews:
        count, confidence = weight.get(review["label"], (0, 0))
        weight[review["label"]] = (count + 1, confidence + review["confidence"])
    ranked = sorted(weight.items(), key=lambda item: item[1], reverse=True)
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return None
    return ranked[0][0]


def wilson(successes: int, total: int) -> tuple[float, float] | None:
    if total <= 0:
        return None
    share = successes / total
    denominator = 1 + Z_95**2 / total
    centre = (share + Z_95**2 / (2 * total)) / denominator
    margin = Z_95 * math.sqrt(share * (1 - share) / total + Z_95**2 / (4 * total**2))
    margin /= denominator
    return round(max(0.0, centre - margin), 4), round(min(1.0, centre + margin), 4)


def _share(part: int, total: int) -> float | None:
    return round(part / total, 4) if total else None


def by_zone(records: Iterable[dict[str, Any]]) -> dict[tuple, list[dict[str, Any]]]:
    zones: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        zones[zone_key(record)].append(record)
    return zones


def statistics(effective: list[dict[str, Any]]) -> dict[str, Any]:
    zones = by_zone(effective)
    verdicts = {key: consensus(reviews) for key, reviews in zones.items()}
    counts = Counter(verdict for verdict in verdicts.values() if verdict is not None)
    disputed = sum(verdict is None for verdict in verdicts.values())
    total = len(zones)
    debris = counts.get(POSITIVE, 0)
    decided = total - disputed - counts.get(UNDECIDED, 0)
    multi = [reviews for reviews in zones.values() if len(reviews) > 1]
    agreed = sum(len({review["label"] for review in reviews}) == 1 for reviews in multi)
    return {
        "reviews": len(effective),
        "zones": total,
        "labels": [
            {
                "label": label.value,
                "title": LABEL_TITLES[label],
                "zones": counts[label],
                "share": _share(counts[label], total),
            }
            for label in ReviewLabel
            if counts.get(label)
        ],
        "disputed": disputed,
        "precision": {
            "debris": debris,
            "zones": total,
            "value": _share(debris, total),
            "interval": wilson(debris, total),
            "decided": decided,
            "decided_value": _share(debris, decided),
        },
        "agreement": {
            "zones": len(multi),
            "agreed": agreed,
            "value": _share(agreed, len(multi)),
        },
    }


def per_aoi(effective: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
    names: dict[str | None, str | None] = {}
    for record in effective:
        groups[record.get("aoi_id")].append(record)
        names[record.get("aoi_id")] = names.get(record.get("aoi_id")) or record.get("aoi_name")
    return [
        {"aoi_id": aoi_id, "aoi_name": names[aoi_id], **statistics(records)}
        for aoi_id, records in sorted(groups.items(), key=lambda item: -len(item[1]))
    ]
