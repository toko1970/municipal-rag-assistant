"""Compare one visual extraction candidate with development gold."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from src.visual_validation import validate_gold


@dataclass(frozen=True)
class VisualExtractionMetrics:
    kind: str
    gold_elements: int
    matched_elements: int
    element_recall: float
    important_values_exact: bool
    mean_bbox_iou: float
    gate_passed: bool


def bbox_iou(left: dict[str, float], right: dict[str, float]) -> float:
    intersection_width = max(0.0, min(left["x1"], right["x1"]) - max(left["x0"], right["x0"]))
    intersection_height = max(0.0, min(left["y1"], right["y1"]) - max(left["y0"], right["y0"]))
    intersection = intersection_width * intersection_height
    left_area = (left["x1"] - left["x0"]) * (left["y1"] - left["y0"])
    right_area = (right["x1"] - right["x0"]) * (right["y1"] - right["y0"])
    union = left_area + right_area - intersection
    return intersection / union if union else 0.0


def element_map(extraction: dict[str, Any]) -> dict[tuple[Any, ...], dict[str, float]]:
    kind = extraction["kind"]
    data = extraction["data"]
    if kind == "flowchart":
        node_text = {node["id"]: node["text"] for node in data["nodes"]}
        elements = {
            ("node", node["text"], node["node_type"]): node["bbox"]
            for node in data["nodes"]
        }
        elements.update(
            {
                (
                    "edge",
                    node_text[edge["from"]],
                    node_text[edge["to"]],
                    edge["condition"],
                ): edge["bbox"]
                for edge in data["edges"]
            }
        )
        return elements
    if kind == "timeline":
        return {
            ("event", event["date_or_offset"], event["action"]): event["bbox"]
            for event in data["events"]
        }
    if kind == "table":
        return {
            (
                "cell",
                cell["row"],
                cell["column"],
                cell["row_span"],
                cell["column_span"],
                cell["text"],
            ): cell["bbox"]
            for cell in data["cells"]
        }
    return {
        ("field", field["label"], field["example_value"]): field["bbox"]
        for field in data["fields"]
    }


def evaluate_visual_extraction(
    candidate: dict[str, Any],
    gold: dict[str, Any],
    schema: dict[str, Any],
) -> VisualExtractionMetrics:
    validate_gold(candidate, schema)
    validate_gold(gold, schema)
    if candidate["kind"] != gold["kind"]:
        return VisualExtractionMetrics(
            kind=gold["kind"],
            gold_elements=len(element_map(gold)),
            matched_elements=0,
            element_recall=0.0,
            important_values_exact=False,
            mean_bbox_iou=0.0,
            gate_passed=False,
        )
    expected = element_map(gold)
    actual = element_map(candidate)
    matched = expected.keys() & actual.keys()
    recall = len(matched) / len(expected) if expected else 1.0
    mean_iou = (
        sum(bbox_iou(expected[key], actual[key]) for key in matched) / len(matched)
        if matched
        else 0.0
    )
    exact = expected.keys() == actual.keys()
    return VisualExtractionMetrics(
        kind=gold["kind"],
        gold_elements=len(expected),
        matched_elements=len(matched),
        element_recall=recall,
        important_values_exact=exact,
        mean_bbox_iou=mean_iou,
        gate_passed=exact and recall >= 0.95 and mean_iou >= 0.80,
    )


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON objectではありません: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--gold", required=True, type=Path)
    parser.add_argument("--schema", required=True, type=Path)
    args = parser.parse_args()
    metrics = evaluate_visual_extraction(
        load_json(args.candidate), load_json(args.gold), load_json(args.schema)
    )
    print(json.dumps(asdict(metrics), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
