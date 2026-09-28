"""Compare one visual extraction candidate with development gold."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable
import unicodedata

from src.visual_validation import validate_gold


EVALUATION_REVISION = "visual-extraction-eval-v4"


def comparison_text(value: str | None) -> str | None:
    if value is None:
        return None
    return value.replace("～", "〜")


def format_normalized_text(value: str | None) -> str | None:
    """Remove whitespace and prose separators while preserving value-bearing signs."""

    canonical = comparison_text(value)
    if canonical is None:
        return None
    canonical = unicodedata.normalize("NFKC", canonical)
    return "".join(
        character
        for character in canonical
        if character not in {"、", "。", ",", "・"} and not character.isspace()
    )


@dataclass(frozen=True)
class VisualExtractionMetrics:
    kind: str
    gold_elements: int
    matched_elements: int
    element_recall: float
    important_values_exact: bool
    mean_bbox_iou: float
    format_normalized_matched_elements: int
    format_normalized_element_recall: float
    format_normalized_important_values_exact: bool
    format_normalized_mean_bbox_iou: float
    format_normalization_collision: bool
    gate_passed: bool


def bbox_iou(left: dict[str, float], right: dict[str, float]) -> float:
    intersection_width = max(0.0, min(left["x1"], right["x1"]) - max(left["x0"], right["x0"]))
    intersection_height = max(0.0, min(left["y1"], right["y1"]) - max(left["y0"], right["y0"]))
    intersection = intersection_width * intersection_height
    left_area = (left["x1"] - left["x0"]) * (left["y1"] - left["y0"])
    right_area = (right["x1"] - right["x0"]) * (right["y1"] - right["y0"])
    union = left_area + right_area - intersection
    return intersection / union if union else 0.0


def element_map(
    extraction: dict[str, Any],
    normalize_text: Callable[[str | None], str | None] = comparison_text,
) -> dict[tuple[Any, ...], dict[str, float]]:
    kind = extraction["kind"]
    data = extraction["data"]
    if kind == "flowchart":
        node_text = {
            node["id"]: normalize_text(node["text"]) for node in data["nodes"]
        }
        elements = {
            ("node", normalize_text(node["text"]), node["node_type"]): node["bbox"]
            for node in data["nodes"]
        }
        elements.update(
            {
                (
                    "edge",
                    node_text[edge["from"]],
                    node_text[edge["to"]],
                    normalize_text(edge["condition"]),
                ): edge["bbox"]
                for edge in data["edges"]
            }
        )
        return elements
    if kind == "timeline":
        return {
            (
                "event",
                normalize_text(event["date_or_offset"]),
                normalize_text(event["action"]),
            ): event["bbox"]
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
                normalize_text(cell["text"]),
            ): cell["bbox"]
            for cell in data["cells"]
        }
    return {
        (
            "field",
            normalize_text(field["label"]),
            normalize_text(field["example_value"]),
        ): field["bbox"]
        for field in data["fields"]
    }


def source_element_count(extraction: dict[str, Any]) -> int:
    """Count elements before normalized dictionary keys can collapse them."""

    kind = extraction["kind"]
    data = extraction["data"]
    if kind == "flowchart":
        return len(data["nodes"]) + len(data["edges"])
    if kind == "timeline":
        return len(data["events"])
    if kind == "table":
        return len(data["cells"])
    return len(data["fields"])


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
            format_normalized_matched_elements=0,
            format_normalized_element_recall=0.0,
            format_normalized_important_values_exact=False,
            format_normalized_mean_bbox_iou=0.0,
            format_normalization_collision=False,
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
    normalized_expected = element_map(gold, format_normalized_text)
    normalized_actual = element_map(candidate, format_normalized_text)
    normalization_collision = (
        len(normalized_expected) != source_element_count(gold)
        or len(normalized_actual) != source_element_count(candidate)
    )
    normalized_matched = normalized_expected.keys() & normalized_actual.keys()
    normalized_recall = (
        len(normalized_matched) / len(normalized_expected)
        if normalized_expected
        else 1.0
    )
    normalized_mean_iou = (
        sum(
            bbox_iou(normalized_expected[key], normalized_actual[key])
            for key in normalized_matched
        )
        / len(normalized_matched)
        if normalized_matched
        else 0.0
    )
    normalized_exact = (
        not normalization_collision
        and normalized_expected.keys() == normalized_actual.keys()
    )
    return VisualExtractionMetrics(
        kind=gold["kind"],
        gold_elements=len(expected),
        matched_elements=len(matched),
        element_recall=recall,
        important_values_exact=exact,
        mean_bbox_iou=mean_iou,
        format_normalized_matched_elements=len(normalized_matched),
        format_normalized_element_recall=normalized_recall,
        format_normalized_important_values_exact=normalized_exact,
        format_normalized_mean_bbox_iou=normalized_mean_iou,
        format_normalization_collision=normalization_collision,
        gate_passed=(
            normalized_exact
            and normalized_recall >= 0.95
            and normalized_mean_iou >= 0.80
        ),
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
