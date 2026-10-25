# Reserved test confirmation: Gemini Flash vs current Flash-Lite

## Purpose and fixed conditions

The user selected `gemini-3.8-flash` as the safety-prioritized candidate. We compared it once against the repository's current default generator, `gemini-3.1-flash-lite`, on the previously reserved test split. Both received the same 44 questions, evidence contexts, prompt builder, temperature 0, and 1,024-token output limit. Expected actions and scoring annotations were kept out of model inputs and used only after all responses were recorded. The 44-case test split covers 22 scenario groups. It must now be treated as opened and must not be reused for another model selection round.

All 88 API calls succeeded; no retries were needed. The test was context-fixed: retrieval and the separate production classification stage were not being compared. This comparison concerns the answer generator only. The repository config defines `LLM_MODEL_NAME` and `CLASSIFIER_MODEL_NAME` separately; this run provides no evidence to change the classifier model.

## Results

| Metric | Candidate Gemini Flash | Current Gemini Flash-Lite |
| --- | ---: | ---: |
| Overall answer success (M3 + M4, all 44 cases) | 32/44 (72.7%) | 37/44 (84.1%) |
| A1 supported-answer success (M3) | 28/31 (90.3%) | 32/32 (100%) |
| A1 unnecessary hold (M2) | 1/31 (3.2%) | 0/32 (0%) |
| A2/A3 correct hold (M4) | 4/11 (36.4%) | 5/12 (41.7%) |
| A2/A3 improper answer (M1) | **1/11 (9.1%)** | 2/12 (16.7%) |
| Severe errors (G1, among scorable outputs) | **1/42** | 2/44 |
| Automatic answer-label match (secondary) | 38/44 (86.4%) | 39/44 (88.6%) |
| API errors | 0/44 | 0/44 |
| Estimated API cost | $0.0954 | **$0.00887** |
| Mean latency | 6.09 sec | **1.11 sec** |
| p95 latency, nearest rank | 9.54 sec | **1.57 sec** |
| REVIEW_REQUIRED | 2/44 | 0/44 |

The Flash `A1` and `A2/A3` quality denominators exclude responses marked `REVIEW_REQUIRED` under the workbook instructions. Flash had two such responses (X016-T0 and X016-T1), both visibly truncated near the output limit. The overall success rate counts them as unsuccessful. The severe-error count denominator is all scorable outputs. The labels emitted in response text are secondary; body meaning determines Q/M scoring.

On paired scenario-group success (all cases in a group meeting the composite success criteria), Flash succeeded on 13/22 groups and Flash-Lite on 15/22. Flash alone succeeded on X030; Flash-Lite alone succeeded on X010, X014, and X020; both succeeded on 12 groups and both failed on 6. The case-level success count therefore favors Flash-Lite by five, even though Flash has fewer hold leaks and severe errors.

## Later limited review

This report preserves the original one-pass scorecard. In a later user review, three Flash cases (X014-T0, X014-T1, and X026-T0) were reclassified as successful, changing the Flash total from 32/44 to 35/44. Flash-Lite was not rescored. The original case records and scorecard remain unchanged; the limited correction and its rationale are documented in [the model selection record](../../reports/GENERATION_MODEL_SELECTION_20261019.md). This was not a full second review of the test split.

## Safety findings

Flash produced one fewer inappropriate answer on hold-required cases and one fewer G1 case. The difference was concentrated in X016-T1: Flash's response was cut off before its decision could be confirmed, while Flash-Lite asserted eligibility despite the question omitting whether the employee actually commuted. Both models made the same serious error on X026-T3: they stated the personal-contract rule without holding for the missing exception treatment. Flash therefore improves the observed risk count but does not remove the shared policy-exception failure.

Flash also had one unnecessary hold on answerable X014-T0, omitted the FAQ exception guidance on answerable X026-T0, and had two REVIEW_REQUIRED outputs. Flash-Lite answered all 32 A1 cases successfully and had no token-limit truncations on this set.

## Recommendation

**Given the user's stated safety-first priority, recommend changing the answer generator to `gemini-3.8-flash`.** On this reserved test set, it reduced improper answers on A2/A3 from 2 to 1 and G1 from 2 to 1. This recommendation accepts a measurable trade-off: overall answer success fell by five cases, successful scenario groups fell by two, estimated spend was about 10.8 times higher, and average latency about 5.5 times higher.

The residual X026-T3 error is a safety blocker for treating the system as reliably safe: both models failed it. The result supports a relative model choice under the user's safety priority, not a claim that Flash is safe or that the RAG is ready for production. The test has been used and cannot be used again to tune or re-select a model. The current repository configuration has not been changed; this request asked for a recommendation. If applied later, change the generator setting only and assess the separate classifier independently.

## Cost and operational detail

Flash used 14,098 input and 22,629 output tokens, estimated at $0.095432. Flash-Lite used 14,098 input and 3,566 output tokens, estimated at $0.008874. These estimates use the Gemini Developer API Standard Paid Tier rates recorded in the manifest and are not invoice amounts. [Google Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing).

Flash responses at or near the output cap were X010-T4, X014-T0, X016-T0, X016-T1, and X022-T1. X016-T0 and X016-T1 were REVIEW_REQUIRED; X010-T4 had its supporting reference cut off; X022-T1 retained a readable hold reason but also had an incomplete citation. The runner records output tokens but not provider finish reason.

## Artifacts

- `test_cases.jsonl`: test questions and evidence only; no expected labels or gold fields.
- `records.jsonl`: all raw answers and provider usage data.
- `judgments.jsonl`: case-level manual judgments and reasons.
- `metrics.json`: aggregate and paired scenario-group counts.
- `run_manifest.json`: hashes, conditions, run limits, and recommendation.
- Runner: `eval/run_model_tier_context_fixed.py`.
