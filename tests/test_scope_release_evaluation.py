"""The release gate must reject incomplete runs and unsafe/diagnostic failures."""
from eval.evaluate_scope_release import summarize


def fixtures():
    cases = [{"id": "A-formal", "kind": "known_development", "scenario_id": "A"},
             {"id": "D03", "kind": "diagnostic_control"}]
    tasks = [{"case_id": c["id"], "arm": arm, "repetition": rep}
             for c in cases for arm in ("baseline", "candidate") for rep in (1, 2)]
    records = [{**t, "correct": t["arm"] == "candidate", "status": "SUCCESS"} for t in tasks]
    return cases, tasks, records


def test_gate_requires_complete_safe_diagnostic_and_repeat_success():
    cases, tasks, records = fixtures()
    assert summarize(cases, tasks, records, "COMPLETED", 0)["gate1_pass"]
    assert not summarize(cases, tasks, records[:-1], "RUNNING", 0)["gate1_pass"]
    for field, value in (("unsafe_sufficient", True), ("api_error", "timeout"), ("correct", False)):
        changed = [dict(r) for r in records]
        changed[-1][field] = value
        assert not summarize(cases, tasks, changed, "COMPLETED", 0)["gate1_pass"]
