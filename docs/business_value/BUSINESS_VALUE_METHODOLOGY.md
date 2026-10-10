# Business Value Methodology

Every dollar figure in `BENCHMARKS.md` and the README is already labeled ASSUMPTION or illustrative --
this document is the one place that shows the real constants behind those labels and a sensitivity range
around them, so the figures are auditable rather than opaque. Nothing here introduces a new assumption;
every number below is read directly from `ASSUMPTIONS` in each BP's own
`04_compliance_impact_reporting_packaging_SINGLE_CELL.py` (confirmed identical across BP1/BP2/BP4/BP5)
and `src/aml_riskiq/reporting/report_builder.py`.

## The three constants

| Constant | Value | Basis |
|---|---|---|
| `hours_per_alert_review` | 0.25 (15 minutes) | A common industry planning figure for a single alert's manual triage time. ASSUMPTION. |
| `cost_per_investigator_hour_usd` | $65.00 | A fully-loaded AML analyst cost figure. ASSUMPTION. |
| `illustrative_case_exposure_usd` | $50,000.00 | Illustrative regulatory-exposure-avoidance per real laundering case caught -- explicitly never a specific fine amount or a prediction of actual enforcement cost. ASSUMPTION. |

Two separate figures are derived from these three constants plus the real test-set-measured
false-positive-reduction and true-positive-uplift counts for each BP (themselves real, from each BP's
saved validation report -- not assumptions):

- **False-positive-reduction savings** = (fewer false-positive alerts, real) x `hours_per_alert_review`
  x `cost_per_investigator_hour_usd`.
- **True-positive-uplift illustrative value** = (additional real cases caught, real) x
  `illustrative_case_exposure_usd`.

## Reproducing the platform rollup figures (BP1+BP4+BP5)

Real inputs from `BENCHMARKS.md`'s own rollup row: 853,981 fewer false-positive alerts; +1,959
additional real cases caught.

```
FP-reduction savings = 853,981 x 0.25 x $65.00 = $13,877,191  (reported: $13,877,192 / $13.88M -- rounding)
TP-uplift value       = 1,959 x $50,000.00       = $97,950,000 (reported: $97,950,000 / $97.95M -- exact)
```

Both reproduce `BENCHMARKS.md`'s published figures from the disclosed constants and the real
false-positive/true-positive counts -- confirming the labeled-ASSUMPTION figures are not opaque, they are
exactly what they claim to be: a real measured detection delta, multiplied by three disclosed constants.

## Sensitivity: +/-25% on each constant

A reader skeptical of the specific constants (a different fully-loaded analyst cost, a different
per-case exposure assumption, a different alert-review time) can see the real range below rather than
treat the headline figure as precise.

| Scenario | `hours_per_alert_review` | `cost_per_investigator_hour_usd` | FP-reduction savings |
|---|---|---|---|
| -25% on both | 0.1875 | $48.75 | $7,805,920 |
| Base (reported) | 0.25 | $65.00 | $13,877,191 |
| +25% on both | 0.3125 | $81.25 | $21,683,111 |

| Scenario | `illustrative_case_exposure_usd` | TP-uplift illustrative value |
|---|---|---|
| -25% | $37,500 | $73,462,500 |
| Base (reported) | $50,000 | $97,950,000 |
| +25% | $62,500 | $122,437,500 |

(`hours_per_alert_review` and `cost_per_investigator_hour_usd` are multiplied together, so the
FP-reduction figure is linear in each individually and quadratic-looking in the combined +/-25% case
shown above -- a reader who wants only one constant varied can scale the base figure linearly by that
constant's own ratio.)

## What this methodology does not claim

- These are not measured savings. No real deployment, no real investigator time study, and no real
  enforcement-avoidance outcome underlies any figure in this document or in `BENCHMARKS.md`.
- The underlying false-positive-reduction and true-positive-uplift counts are real (measured on the IBM
  synthetic dataset's held-out test split), but extrapolating them to dollars requires the three ASSUMPTION
  constants above -- which is exactly what every dollar figure in this platform's reporting already
  discloses, and what this document now shows the arithmetic for.
