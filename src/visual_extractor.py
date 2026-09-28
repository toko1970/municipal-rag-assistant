"""Gemini visual extraction boundary that always produces a review candidate."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Protocol

from src.llm_provider import StructuredLLMResult
from src.visual_ingestion import RenderedPage, load_visual_schema
from src.visual_validation import validate_gold


VISUAL_EXTRACTION_PROMPT_VERSION = "visual-extraction-v1"


class MultimodalStructuredProvider(Protocol):
    def generate_structured_multimodal(
        self,
        prompt: str,
        schema: dict[str, Any],
        *,
        image: bytes,
        mime_type: str,
    ) -> StructuredLLMResult: ...


@dataclass(frozen=True)
class VisualExtractionCandidate:
    raw_data: dict[str, Any]
    data: dict[str, Any]
    provider: str
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    request_id: str
    validation_errors: tuple[str, ...] = ()
    normalized_bbox_count: int = 0
    normalized_structure_count: int = 0


def build_visual_extraction_prompt(*, page_number: int, kind_hint: str) -> str:
    return f"""あなたは日本語の自治体人事・給与文書を構造化する抽出器です。
添付ページ内の主な図表を、指定されたJSON Schemaに従って1件抽出してください。

- pageは{page_number}です。
- 想定kindは{kind_hint}です。画像と矛盾する場合だけ実際のkindを返してください。
- bboxはページ左上を原点とし、幅と高さを1とする0から1の座標です。
- bboxは小数第4位へ丸めてください。
- bboxは始点・終点ではなく、対象を囲む矩形です。常にx0 < x1かつy0 < y1にしてください。
- 縦線・横線・矢印も線の太さと条件ラベルを含む、幅と高さが0でない矩形で囲んでください。
- 読めない文字、曖昧な矢印、接続先を推測しないでください。
- confidenceは自己申告であり、自動承認には使われません。
- 図表は必ず人が確認するためreview_requiredはtrueにしてください。
"""


def normalize_candidate_bboxes(value: Any) -> int:
    """Convert endpoint-like coordinates into bounded non-zero rectangles."""

    normalized = 0
    if isinstance(value, dict):
        keys = {"x0", "y0", "x1", "y1"}
        if keys.issubset(value):
            original = tuple(value[key] for key in ("x0", "y0", "x1", "y1"))
            x0, x1 = sorted((float(value["x0"]), float(value["x1"])))
            y0, y1 = sorted((float(value["y0"]), float(value["y1"])))
            if x0 == x1:
                x0, x1 = _expand_coordinate(x0)
            if y0 == y1:
                y0, y1 = _expand_coordinate(y0)
            replacement = tuple(round(item, 4) for item in (x0, y0, x1, y1))
            value.update(dict(zip(("x0", "y0", "x1", "y1"), replacement)))
            normalized += replacement != original
        for child in value.values():
            normalized += normalize_candidate_bboxes(child)
    elif isinstance(value, list):
        for child in value:
            normalized += normalize_candidate_bboxes(child)
    return normalized


def _expand_coordinate(value: float, half_width: float = 0.0005) -> tuple[float, float]:
    if value <= half_width:
        return 0.0, half_width * 2
    if value >= 1 - half_width:
        return 1 - half_width * 2, 1.0
    return value - half_width, value + half_width


def normalize_table_dimensions(candidate: dict[str, Any]) -> int:
    if candidate.get("kind") != "table":
        return 0
    data = candidate.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("cells"), list):
        return 0
    cells = data["cells"]
    if not cells:
        return 0
    required_rows = max(cell["row"] + cell["row_span"] for cell in cells)
    required_columns = max(
        cell["column"] + cell["column_span"] for cell in cells
    )
    changes = 0
    if isinstance(data.get("row_count"), int) and data["row_count"] < required_rows:
        data["row_count"] = required_rows
        changes += 1
    if (
        isinstance(data.get("column_count"), int)
        and data["column_count"] < required_columns
    ):
        data["column_count"] = required_columns
        changes += 1
    return changes


def normalize_flowchart_roles(candidate: dict[str, Any]) -> int:
    """Infer start/end roles only from one connected, unambiguous graph."""

    if candidate.get("kind") != "flowchart":
        return 0
    data = candidate.get("data")
    if not isinstance(data, dict):
        return 0
    nodes = data.get("nodes")
    edges = data.get("edges")
    if not isinstance(nodes, list) or not nodes or not isinstance(edges, list):
        return 0
    node_by_id = {node.get("id"): node for node in nodes}
    if None in node_by_id or len(node_by_id) != len(nodes):
        return 0
    known_ids = set(node_by_id)
    if any(
        edge.get("from") not in known_ids or edge.get("to") not in known_ids
        for edge in edges
    ):
        return 0

    incoming = {node_id: 0 for node_id in known_ids}
    outgoing = {node_id: [] for node_id in known_ids}
    for edge in edges:
        incoming[edge["to"]] += 1
        outgoing[edge["from"]].append(edge["to"])
    roots = [node_id for node_id, count in incoming.items() if count == 0]
    if len(roots) != 1:
        return 0
    reachable = {roots[0]}
    pending = [roots[0]]
    while pending:
        current = pending.pop()
        for destination in outgoing[current]:
            if destination not in reachable:
                reachable.add(destination)
                pending.append(destination)
    if reachable != known_ids:
        return 0

    root = node_by_id[roots[0]]
    start_nodes = [node for node in nodes if node.get("node_type") == "start"]
    changes = 0
    if not start_nodes and root.get("node_type") == "process":
        root["node_type"] = "start"
        changes += 1
    elif len(start_nodes) != 1 or start_nodes[0] is not root:
        return 0

    for node_id, destinations in outgoing.items():
        node = node_by_id[node_id]
        if not destinations and node.get("node_type") == "process":
            node["node_type"] = "end"
            changes += 1
    return changes


def extract_visual_candidate(
    *,
    page: RenderedPage,
    kind_hint: str,
    provider: MultimodalStructuredProvider,
) -> VisualExtractionCandidate:
    schema = load_visual_schema()
    result = provider.generate_structured_multimodal(
        build_visual_extraction_prompt(
            page_number=page.page_number,
            kind_hint=kind_hint,
        ),
        schema,
        image=page.png,
        mime_type="image/png",
    )
    return prepare_visual_candidate(result=result, page=page)


def prepare_visual_candidate(
    *, result: StructuredLLMResult, page: RenderedPage
) -> VisualExtractionCandidate:
    schema = load_visual_schema()
    raw_data = deepcopy(result.data)
    candidate = deepcopy(result.data)
    candidate["schema_version"] = "1.0"
    candidate["page"] = page.page_number
    candidate["source_image_sha256"] = page.sha256
    confidence = candidate.get("confidence")
    if not isinstance(confidence, dict):
        confidence = {
            "source": "unavailable",
            "value": None,
        }
        candidate["confidence"] = confidence
    confidence["review_required"] = True
    normalized_bbox_count = normalize_candidate_bboxes(candidate)
    normalized_structure_count = normalize_table_dimensions(candidate)
    normalized_structure_count += normalize_flowchart_roles(candidate)
    validation_errors: tuple[str, ...] = ()
    try:
        validate_gold(candidate, schema)
    except ValueError as error:
        validation_errors = (str(error),)
    return VisualExtractionCandidate(
        raw_data=raw_data,
        data=candidate,
        provider=result.provider,
        model=result.model,
        prompt_version=VISUAL_EXTRACTION_PROMPT_VERSION,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        request_id=result.request_id,
        validation_errors=validation_errors,
        normalized_bbox_count=normalized_bbox_count,
        normalized_structure_count=normalized_structure_count,
    )
