# Free-form candidate production rollout decision

- Decision date: 2026-10-25
- Decision: proceed with production integration, directed by the user
- Candidate prompt SHA-256: `cae1bafc46a98a30670f6e32c79508514a25580d80ba8f2a5d370e63a786ac0d`
- Production deployment: not performed by this change

## Basis

The user reviewed the direct paired comparison of the current production path and the free-form candidate on the initial 130 questions and the new 80-expression challenge set. The user found no response differences requiring correction and directed that the candidate be integrated into the production path.

On the direct comparison, the candidate had five candidate-only M3 wins and no production-only M3 wins on each set. On the 80-expression challenge set, Q4 had seven candidate-only wins and one production-only win. Both systems were judged to have no unsupported assertion on all 80 expressions; this measure did not distinguish the systems.

## Prior sealed result retained

The candidate-specific fresh sealed holdout dated 2026-10-24 uses the same prompt SHA and remains a **No-go** under its frozen thresholds:

- end-to-end composite success: 76/100 against a 95% threshold;
- classification macro F1: 0.7691 against 0.80;
- evidence hit@5: 86.25% against 90%;
- evidence hit@3: 77.50% against 80%;
- p95 latency: 10.848 seconds against a 10-second goal;
- critical unsupported assertions: 0/100, and content accuracy: 100/100.

The holdout is consumed and was not reopened or reused. This production integration follows the user's explicit decision based on the separate direct paired comparison; it does not change or relabel the sealed evaluation as a pass. The sealed result remains an operational risk and should accompany any deployment review.

## Implementation scope

- Route the configured candidate through the shared Qdrant composition root for the Streamlit app and CLI.
- Keep request, retrieval, generation, answer, and feedback records associated with the existing PostgreSQL request ID. Free-form answers have no separate classifier attempt or claim-level evidence links; the parsed label and retrieved references remain available.
- Configure the Cloud Run bootstrap and service deployment workflow for `autoresearch_candidate` and Gemini 3.8 Flash.
- Keep local default flow as `production`; the candidate is selected explicitly by the Cloud Run workflow.

## Verification and remaining release steps

- Non-integration tests: 522 passed; 3 deselected.
- Ruff on the changed application and test files: passed.
- Full working-tree Ruff: currently reports existing issues in unrelated experimental evaluation files; the working tree contained unrelated uncommitted work before this rollout change.
- PostgreSQL/Qdrant integration tests were not run because the local Docker daemon was unavailable.
- The Cloud Run deployment workflow updates production only after changes reach `main` and the GitHub `production` environment approval is granted. No merge, push, or deployment has occurred here.
