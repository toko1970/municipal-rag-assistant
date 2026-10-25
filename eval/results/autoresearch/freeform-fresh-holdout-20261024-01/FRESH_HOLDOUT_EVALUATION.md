# Fresh sealed holdout evaluation

- Date: 2026-10-24
- Candidate: `candidate-visual-table-notes-20261024-01`
- Holdout: `text-sealed-holdout-fresh-20261024` (50 scenarios / 100 expressions)
- Prediction run: `freeform-fresh-holdout-20261024-01`
- Prediction SHA-256: `11def2d5511d7e7bb294e346c82dcb05b668aa94afe507f39bc36fafd14844e1`
Custodian scoring: completed; manifest state is `CONSUMED`.

## Decision

**No-go for applying this candidate to production traffic.** The candidate misses several pre-fixed quality and safety gates. Its high content-accuracy result does not offset failures in retrieval, classification, end-to-end success, and the zero-tolerance unsupported-assertion gate. The consumed holdout must not be reused to tune or re-evaluate this candidate; a revised candidate needs a new independent holdout.

## Frozen acceptance gates

| Metric | Result | Fixed threshold | Status |
|---|---:|---:|---|
| Evidence hit@5 | 69/80 (86.25%) | ≥90% | Fail |
| Evidence hit@3 | 62/80 (77.50%) | ≥80% | Fail |
| Content accuracy | 100/100 (100%) | ≥85% | Pass |
| Classification macro F1 | 0.7691 | ≥0.80 | Fail |
| Critical unsupported assertions | 0/100 after polarity correction | 0 | Pass |
| End-to-end composite success | 76/100 (76%) | ≥95% | Fail |
| External API errors | 0/100 (0%) | ≤5% | Pass |
| p95 latency | 10.848s | ≤10s goal | Missed |
| Estimated cost per expression | $0.003756 | ≤$0.01 goal | Pass |

Scenario stability was 35/50 (70%). The 95% Wilson interval for composite success was 66.77%–83.31%.

The custodian initially used the opposite boolean polarity. Per the user clarification, the submitted 100 `true` values mean no critical unsupported assertion was found; after polarity correction, the count is 0/100 and this gate passes. The raw review file was preserved unchanged; the correction and superseded aggregate hash are in `custodian-score/flag_polarity_correction.json`.

## Operational run

All 100 generations completed; provider errors and additional 429 retries were both zero. Estimated total cost was $0.3756055, including a $0.10 reserve for embeddings. The p95 latency target was missed (maximum 44.810s). No judge calls were used.

## Interpretation and next step

The candidate should not be sent to production traffic. The safety gate passes after correcting the flag polarity, but evidence hit@5, evidence hit@3, classification macro F1, and end-to-end success remain below their fixed thresholds. Do not use this consumed holdout to choose or tune a successor. Any revised candidate must be frozen on development evidence and evaluated on a newly created sealed holdout.

Source aggregate: `custodian-score/results.json`. Prediction/run evidence: `summary.json`, `run_manifest.json`, and `FRESH_HOLDOUT_HANDOFF.md` in this directory.
