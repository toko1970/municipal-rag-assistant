import copy
import json
from pathlib import Path

from src.llm_provider import StructuredLLMResult
from src.visual_extractor import extract_visual_candidate, normalize_candidate_bboxes
from src.visual_ingestion import render_pdf_page


ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "eval/visual_fixtures/documents/flowchart_dev_001.pdf"
GOLD = ROOT / "eval/visual_fixtures/gold/flowchart_dev_001.json"


class FakeMultimodalProvider:
    def __init__(self, data: dict) -> None:
        self.data = data
        self.call = None

    def generate_structured_multimodal(
        self, prompt, schema, *, image, mime_type
    ) -> StructuredLLMResult:
        self.call = {
            "prompt": prompt,
            "schema": schema,
            "image": image,
            "mime_type": mime_type,
        }
        return StructuredLLMResult(
            provider="fake",
            model="visual-test",
            data=copy.deepcopy(self.data),
            input_tokens=100,
            output_tokens=50,
            request_id="request-1",
        )


def candidate_data() -> dict:
    return json.loads(GOLD.read_text(encoding="utf-8"))


def test_visual_extractor_binds_page_hash_and_forces_review() -> None:
    page = render_pdf_page(PDF, 1)
    candidate = candidate_data()
    candidate["page"] = 99
    candidate["source_image_sha256"] = "0" * 64
    candidate["confidence"]["review_required"] = False
    provider = FakeMultimodalProvider(candidate)

    result = extract_visual_candidate(
        page=page, kind_hint="flowchart", provider=provider
    )

    assert result.data["page"] == 1
    assert result.data["source_image_sha256"] == page.sha256
    assert result.data["confidence"]["review_required"] is True
    assert result.prompt_version == "visual-extraction-v1"
    assert result.input_tokens == 100
    assert provider.call["image"] == page.png
    assert provider.call["mime_type"] == "image/png"
    assert "推測しない" in provider.call["prompt"]
    assert "始点・終点ではなく" in provider.call["prompt"]


def test_visual_extractor_rejects_semantically_invalid_result() -> None:
    candidate = candidate_data()
    candidate["data"]["edges"][0]["to"] = "unknown-node"

    result = extract_visual_candidate(
        page=render_pdf_page(PDF, 1),
        kind_hint="flowchart",
        provider=FakeMultimodalProvider(candidate),
    )

    assert len(result.validation_errors) == 1
    assert "未知のnode" in result.validation_errors[0]


def test_normalize_candidate_bboxes_sorts_and_expands_line_coordinates() -> None:
    value = {
        "vertical": {"x0": 0.5, "y0": 0.8, "x1": 0.5, "y1": 0.2},
        "horizontal": {"x0": 0.9, "y0": 0.4, "x1": 0.1, "y1": 0.4},
    }

    count = normalize_candidate_bboxes(value)

    assert count == 2
    assert value["vertical"] == {
        "x0": 0.4995,
        "y0": 0.2,
        "x1": 0.5005,
        "y1": 0.8,
    }
    assert value["horizontal"] == {
        "x0": 0.1,
        "y0": 0.3995,
        "x1": 0.9,
        "y1": 0.4005,
    }
