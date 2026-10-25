# Gemini Flash / Pro context-fixed development comparison

- Run: `model-tier-context-fixed-development-20261019`
- Status: development comparison complete; no adoption decision made.
- Source: approved `development` split of the 90-case review workbook. This run used 46 cases from 23 scenario groups (35 A1, 5 A2, 6 A3). The 44-case `test` split remains reserved and was not used for generation or scoring.
- Conditions: identical question, evidence context, and `src.rag_chain.build_prompt`; temperature 0; output cap 1,024; 46 cases per model. Both models have 46 successful final outputs.
- Model IDs: `gemini-3.8-flash` and `gemini-3.1-pro-preview`.

## Results

| Metric (approved workbook rubric) | Gemini Flash | Gemini Pro |
| --- | ---: | ---: |
| Overall answer success (A1 M3 + A2/A3 M4) | 34/46 (73.9%) | 30/46 (65.2%) |
| A1 supported-answer success (M3) | 33/35 (94.3%) | 30/35 (85.7%) |
| A2/A3 correct hold success (M4) | 1/10 (10.0%) | 0/10 (0.0%) |
| A2/A3 inappropriate answer / hold leakage (M1) | 1/10 (10.0%) | 1/10 (10.0%) |
| A1 unnecessary hold (M2) | 0/35 (0%) | 0/35 (0%) |
| Q1 correct action on scored A2/A3 cases | 9/10 (90.0%) | 9/10 (90.0%) |
| Q2 reason for hold correct | 8/10 (80.0%) | 8/10 (80.0%) |
| Q3 useful next step / missing information | 1/10 (10.0%) | 0/10 (0.0%) |
| G1 severe unsupported current-policy assertion | 1/46 (2.2%) | 1/46 (2.2%) |
| Automatic answer-label accuracy (secondary only) | 44/46 (95.7%) | 45/46 (97.8%) |
| Estimated API cost | $0.0908 | $0.3939 |

Overall success counts use the workbook’s two distinct success paths: a correct supported answer for A1 and a correct hold for A2/A3. `Q1`–`Q3` denominators exclude one `REVIEW_REQUIRED` case per model because the generated answer was cut off at the output limit and its rubric classification could not be reliably decided. Those cases remain failures in the overall success count. Q4 is reflected in A1/M3: Flash had 2 A1 misses and Pro 5, including missing answer details or truncated citations. Q2 and Q3 are judged against the approved case-specific expected reasons and actionable next steps, not merely whether a hold phrase appeared.

## Interpretation

On this development split, Flash leads the primary overall success metric by 4 cases (8.7 percentage points) and is substantially less costly (about 4.3× lower estimated spend). Pro has a one-case advantage on the automatic answer-label metric, but that label is not the workbook’s primary quality measure. Both models made the same severe error on X013-T2 by stating the obsolete 2 km commuting-distance requirement as current. Both also struggled to name case-specific missing information or an actionable confirmation step on hold-required cases. The observed counts are per case; 46 cases include paired variants from only 23 scenario groups, so these results are development evidence, not an independent generalization estimate.

**Provisional candidate for the next confirmation stage: Gemini Flash**, based on this development-only result. Lock the candidate before running the reserved test split; do not tune on that split. This report does not claim statistical significance or authorize deployment.

## Execution note

During API-key rotation, the initial requests for X045-T0 and X045-T4 failed for both models (4 failures). After the user confirmed the new key was saved and requested resumption, those exact four failed pairs were retried once; all four succeeded. The successful retry answers are used for scoring. The original failed attempts remain in `records.jsonl` for audit. Total attempts: 96; successful final case/model pairs: 92/92.

Three Flash/Pro outputs reached 1,020 output tokens, near the configured 1,024 cap (Flash: X003-T4, X013-T2; Pro: X013-T2, X027-T0, X031-T2). Truncated/incomplete responses were scored according to the visible content and the workbook’s `REVIEW_REQUIRED` guidance where the intended response could not be determined. The runner does not log the provider finish reason, so cap-related truncation is indicated by the token counts and visibly incomplete text rather than a provider termination code.

Cost is estimated from returned token usage and the official Gemini API rates recorded in the run manifest; it is not an invoice amount and may exclude taxes or other charges. [Google Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing).

## Artifacts and reproducibility

- `development_cases.jsonl`: extracted approved development cases only; no test split content.
- `records.jsonl`: all 96 attempts, including original failures and successful retries.
- `run_manifest.json`: source and input hashes, prompt/model conditions, rates, retry authorization, and scoring scope.
- Runner: `eval/run_model_tier_context_fixed.py`.

Scoring was a manual review of returned answer text using the workbook’s approved criteria; automatic classification labels were reported separately. Because reviewer decisions may involve interpretation, use the case-level workbook and `records.jsonl` together when auditing individual cases. The workbook itself was left unchanged.
