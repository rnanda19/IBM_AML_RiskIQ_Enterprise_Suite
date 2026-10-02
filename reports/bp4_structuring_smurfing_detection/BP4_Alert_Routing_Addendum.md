# BP4 -- Real Alert-Routing & Capacity-Planning Addendum (LI-Medium)

_Generated 2026-10-01T18:08:05.904605+00:00 UTC. Reads Notebook 3's real saved `alert_routing_policy` -- nothing recomputed here._

## ACTION NEEDED
`CAPACITY_ASSUMPTIONS` in this notebook's Section 9 are PLACEHOLDERS (`alerts_per_analyst_per_day=40`, `analysts_available=5`), not real staffing figures. Replace them with real numbers before treating this addendum's queue-depth read as more than illustrative.

## Real Alert-Routing Tiers
Method: percentile (top real decile of flagged test-set alerts)

| Tier | Alerts | Real precision within tier |
|---|---|---|
| 1 -- Auto-SAR-Recommend | 1,433 | 30.8% |
| 2 -- Structuring-Investigator-Queue | 12,751 | 6.1% |

## Illustrative Capacity Read (ASSUMPTION -- replace CAPACITY_ASSUMPTIONS above with real figures)
At 200 alerts/day (5 analysts x 40/day, PLACEHOLDER), Tier 2's 12,751 real alerts would take ~63.8 days to clear.