"""Cross-BP alert deduplication/grouping. See the casework package docstring for scope.

This groups alerts that reference the SAME entity within a time window -- it does not claim
the grouped alerts are duplicates of the same detection (a BP1 transaction-monitoring alert
and a BP4 structuring alert on the same account on the same day are two distinct, real
detections an investigator should see together, not a false-positive duplicate to collapse
into one)."""

from __future__ import annotations

from .alert_schema import Alert

DEFAULT_WINDOW_HOURS = 24.0


def cluster_alerts(alerts: list[Alert], *, window_hours: float = DEFAULT_WINDOW_HOURS) -> list[list[Alert]]:
    """Groups alerts by entity_ref, then splits each entity's alerts into clusters where
    consecutive (by scoring_timestamp) alerts are within `window_hours` of each other.
    Returns clusters sorted by their earliest scoring_timestamp; a singleton cluster is a
    normal result for an entity with only one alert in range, not an error."""
    by_entity: dict[str, list[Alert]] = {}
    for a in alerts:
        by_entity.setdefault(a.entity_ref, []).append(a)

    clusters: list[list[Alert]] = []
    for entity_alerts in by_entity.values():
        ordered = sorted(entity_alerts, key=lambda a: a.scoring_timestamp)
        current: list[Alert] = []
        for a in ordered:
            if (
                current
                and (a.scoring_timestamp - current[-1].scoring_timestamp).total_seconds()
                > window_hours * 3600
            ):
                clusters.append(current)
                current = []
            current.append(a)
        if current:
            clusters.append(current)

    return sorted(clusters, key=lambda c: c[0].scoring_timestamp)


def exact_duplicates(alerts: list[Alert]) -> list[Alert]:
    """Returns alerts that are true duplicates -- identical (entity_ref, transaction_ref,
    business_problem, detection_source, selected_threshold) to an already-seen alert. Unlike
    cluster_alerts(), this IS a same-detection duplicate (e.g. a retried /score call that
    produced two Alert objects for the one real event) and is safe to collapse. Keeps the
    first occurrence of each key, returns the rest (the ones a caller should discard)."""
    seen: set[tuple] = set()
    duplicates: list[Alert] = []
    for a in alerts:
        key = (a.entity_ref, a.transaction_ref, a.business_problem, a.detection_source, a.selected_threshold)
        if key in seen:
            duplicates.append(a)
        else:
            seen.add(key)
    return duplicates
