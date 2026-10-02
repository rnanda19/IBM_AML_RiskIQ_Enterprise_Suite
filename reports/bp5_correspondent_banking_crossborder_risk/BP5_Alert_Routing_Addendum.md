# BP5 -- Real Alert-Routing & Capacity-Planning Addendum (LI-Medium)

_Generated 2026-10-02T11:30:31.233259+00:00 UTC. Reads Notebook 3's real saved `alert_routing_policy` -- nothing recomputed here._

## ACTION NEEDED
`CAPACITY_ASSUMPTIONS` in this notebook's Section 9 are PLACEHOLDERS (`alerts_per_analyst_per_day=40`, `analysts_available=5`), not real staffing figures. Replace them with real numbers before treating this addendum's queue-depth read as more than illustrative.

## Real Alert-Routing Tiers
Method: percentile (top real decile of flagged test-set alerts by calibrated probability)

| Tier | Alerts | Real precision within tier |
|---|---|---|
| 1 -- Auto-SAR-Recommend | 445 | 74.6% |
| 2 -- Correspondent-Banking-Investigator-Queue | 3,719 | 10.8% |

## Illustrative Capacity Read (ASSUMPTION -- replace CAPACITY_ASSUMPTIONS above with real figures)
At 200 alerts/day (5 analysts x 40/day, PLACEHOLDER), Tier 2's 3,719 real alerts would take ~18.6 days to clear.

## OFAC Sanctions-Screening Note
OFAC sanctions-list screening: Not Possible - Data Limitation. Cross-border wires are the single highest-risk channel for a sanctioned-party hit, and real correspondent-banking programs run every cross-border wire against OFAC's SDN and related sanctions lists -- but the IBM AML transaction dataset has no real sanctions-list, watchlist, or entity-name field this notebook or Notebook 3 could screen against. This capability gap is disclosed here explicitly, never silently omitted or implied as already done.