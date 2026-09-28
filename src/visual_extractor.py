"""Gemini visual extraction boundary that always produces a review candidate."""

from __future__ import annotations

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
    data: dict[str, Any]
    provider: str
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    request_id: str
    validation_errors: tuple[str, ...] = ()
    normalized_bbox_count: int = 0


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
    candidate = dict(result.data)
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
    validation_errors: tuple[str, ...] = ()
    try:
        validate_gold(candidate, schema)
    except ValueError as error:
        validation_errors = (str(error),)
    return VisualExtractionCandidate(
        data=candidate,
        provider=result.provider,
        model=result.model,
        prompt_version=VISUAL_EXTRACTION_PROMPT_VERSION,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        request_id=result.request_id,
        validation_errors=validation_errors,
        normalized_bbox_count=normalized_bbox_count,
    )
