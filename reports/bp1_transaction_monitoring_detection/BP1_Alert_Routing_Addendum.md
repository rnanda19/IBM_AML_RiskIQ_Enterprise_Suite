# BP1 -- Real Alert-Routing & Capacity-Planning Addendum (LI-Medium)

_Generated 2026-10-01T06:45:58.029009+00:00 UTC. Reads Notebook 3's real saved `alert_routing_policy` -- nothing recomputed here._

## ACTION NEEDED
`CAPACITY_ASSUMPTIONS` in this notebook's Section 9 are PLACEHOLDERS (`alerts_per_analyst_per_day=40`, `analysts_available=5`), not real staffing figures. Replace them with real numbers before treating this addendum's queue-depth read as more than illustrative.

## Real Alert-Routing Tiers
Method: percentile (top real decile of flagged test-set alerts by calibrated probability)

| Tier | Alerts | Real precision within tier |
|---|---|---|
| 1 -- Auto-SAR-Recommend | 542 | 65.3% |
| 2 -- Investigator-Queue | 4,529 | 8.1% |
| 3 -- Graph-Investigation-Queue | reserved | BP3 (Transaction Network & Graph Intelligence) not yet built -- this tier is reserved, not yet populated by a real signal. |

## Illustrative Capacity Read (ASSUMPTION -- replace CAPACITY_ASSUMPTIONS above with real figures)
At 200 alerts/day (5 analysts x 40/day, PLACEHOLDER), Tier 2's 4,529 real alerts would take ~22.6 days to clear.