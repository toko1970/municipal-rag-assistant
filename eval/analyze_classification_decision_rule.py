"""Apply the deterministic classification rule to a frozen prompt comparison."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.answering import derive_label, parse_classification_output


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON top-level must be object: {path}")
    return value


def analyze(bundle: dict[str, Any], dataset: dict[str, Any]) -> dict[str, Any]:
    cases = {case["case_id"]: case for case in dataset["cases"]}
    if {record["case_id"] for record in bundle["records"]} != set(cases):
        raise ValueError("comparisonとdatasetのcase IDが一致しません")
    records = []
    for record in bundle["records"]:
        if record["error"] is not None or record["response"] is None:
            continue
        raw = parse_classification_output(record["response"])
        effective_label = derive_label(raw.factors)
        records.append(
            {
                "case_id": record["case_id"],
                "modality": record["modality"],
                "prompt": record["prompt"],
                "expected_label": record["expected_label"],
                "raw_label": record["predicted_label"],
                "effective_label": effective_label,
                "raw_correct": record["correct"],
                "effective_correct": effective_label == record["expected_label"],
                "raw_factors": record["response"]["factors"],
                "effective_factors": record["response"]["factors"],
            }
        )
    by_prompt = {}
    for prompt in dict.fromkeys(record["prompt"] for record in records):
        selected = [record for record in records if record["prompt"] == prompt]
        by_prompt[prompt] = {
            "count": len(selected),
            "raw_correct": sum(record["raw_correct"] for record in selected),
            "effective_correct": sum(
                record["effective_correct"] for record in selected
            ),
            "raw_accuracy": (
                sum(record["raw_correct"] for record in selected) / len(selected)
                if selected
                else None
            ),
            "effective_accuracy": (
                sum(record["effective_correct"] for record in selected) / len(selected)
                if selected
                else None
            ),
            "text_effective_correct": sum(
                record["effective_correct"]
                for record in selected
                if record["modality"] == "text"
            ),
            "visual_effective_correct": sum(
                record["effective_correct"]
                for record in selected
                if record["modality"] == "visual"
            ),
        }
    return {"summary": {"by_prompt": by_prompt}, "records": records}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"結果は上書きしません: {args.output}")
    result = analyze(_load_json(args.comparison), _load_json(args.dataset))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
