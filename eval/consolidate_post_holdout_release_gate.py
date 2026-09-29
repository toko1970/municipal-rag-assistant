"""Consolidate the fixed 130-question result and targeted deadline evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def consolidate(
    integrated: dict[str, Any],
    route_audit: dict[str, Any],
    deadline_e2e: dict[str, Any],
) -> dict[str, Any]:
    candidate = integrated["candidate"]
    audit_summary = route_audit["summary"]
    no_regression_impact = (
        audit_summary["formal_changed_questions"] == 0
        and audit_summary["formal_current_route_positive"] == 0
    )
    return {
        "assessment": "post-holdout-targeted-release-gate-v1",
        "development_regression": {
            "success": candidate["success"],
            "total": candidate["total"],
            "success_rate": candidate["success_rate"],
            "result_reused": True,
            "reason": (
                "固定500問のformal 100問で日付route変更対象が0件で、"
                "図表30問は別経路のため"
            ),
        },
        "deadline_route_corpus_audit": audit_summary,
        "deadline_e2e": deadline_e2e,
        "release_gate_passed": bool(
            integrated["impact_gate_passed"]
            and no_regression_impact
            and deadline_e2e["gate_passed"]
        ),
        "new_external_api_calls": deadline_e2e["logical_external_calls"],
        "new_estimated_cost_usd": deadline_e2e["estimated_cost_usd"],
        "sealed_holdout_reused": False,
        "production_deployed": False,
        "claim_boundary": (
            "120/130は既存development回帰の維持値であり、日付改善による上昇値ではない。"
            "日付改善の新規証拠はtargeted end-to-end 4/4である。"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--integrated-summary", type=Path, required=True)
    parser.add_argument("--route-audit", type=Path, required=True)
    parser.add_argument("--deadline-e2e-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"output already exists: {args.output}")

    result = consolidate(
        _load(args.integrated_summary),
        _load(args.route_audit),
        _load(args.deadline_e2e_summary),
    )
    result["source_sha256"] = {
        str(path): _sha256(path)
        for path in (
            args.integrated_summary,
            args.route_audit,
            args.deadline_e2e_summary,
        )
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
