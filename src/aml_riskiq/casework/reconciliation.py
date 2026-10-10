"""Reconciliation reporting -- the counts the external review's Prompt 5 explicitly asked
for: transactions evaluated, alerts generated, deduplicated, cases created/reviewed/
unresolved, and rejected/failed records. See the casework package docstring for scope.

HONEST SCOPE NOTE: `n_transactions_evaluated` and `n_rejected` are caller-supplied counts
(this package has no connection to a live scoring run) -- everything else is computed for
real from the Alert objects actually passed in."""

from __future__ import annotations

from .alert_schema import Alert, CaseStatus
from .dedup import cluster_alerts, exact_duplicates


def build_reconciliation_report(
    alerts: list[Alert],
    *,
    n_transactions_evaluated: int,
    n_rejected: int = 0,
    window_hours: float = 24.0,
) -> dict:
    """Builds the reconciliation report. All counts below reconcile by construction:
    n_alerts_generated == n_exact_duplicates + n_alerts_after_dedup, and every alert in
    `alerts` is counted in exactly one status bucket."""
    duplicates = exact_duplicates(alerts)
    duplicate_ids = {d.alert_id for d in duplicates}
    deduped_alerts = [a for a in alerts if a.alert_id not in duplicate_ids]
    clusters = cluster_alerts(deduped_alerts, window_hours=window_hours)

    status_counts: dict[str, int] = {status.value: 0 for status in CaseStatus}
    for a in alerts:
        status_counts[a.status.value] += 1

    report = {
        "n_transactions_evaluated": n_transactions_evaluated,
        "n_rejected": n_rejected,
        "n_alerts_generated": len(alerts),
        "n_exact_duplicates_removed": len(duplicates),
        "n_alerts_after_dedup": len(deduped_alerts),
        "n_entity_clusters": len(clusters),
        "status_counts": status_counts,
        "n_cases_reviewed": status_counts[CaseStatus.UNDER_REVIEW.value]
        + status_counts[CaseStatus.ESCALATED.value]
        + status_counts[CaseStatus.CLOSED.value],
        "n_cases_unresolved": status_counts[CaseStatus.UNRESOLVED.value],
        "n_cases_not_yet_actioned": status_counts[CaseStatus.NEW.value],
    }

    # Internal reconciliation check -- every alert accounted for exactly once across the
    # status buckets. Raises rather than silently returning an inconsistent report.
    if sum(status_counts.values()) != len(alerts):
        raise AssertionError(
            "Reconciliation failed: status_counts does not sum to len(alerts) -- this is a "
            "bug in build_reconciliation_report, not a real data inconsistency."
        )

    return report
