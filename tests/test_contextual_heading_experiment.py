import json
from types import SimpleNamespace

import pytest

from eval.compare_contextual_heading import (
    contextual_document_text,
    load_baseline_query_vectors,
)


def test_contextual_text_adds_document_and_full_heading_without_mutation() -> None:
    element = SimpleNamespace(
        document_name="届出・手続きマニュアル",
        content="## 4.2 提出期限\n変更日から10日以内に提出すること。",
        metadata={
            "見出し1": "4. 通勤経路変更届",
            "見出し2": "4.2 提出期限",
        },
    )

    result = contextual_document_text(element)

    assert result.startswith(
        "文書: 届出・手続きマニュアル\n"
        "見出し: 4. 通勤経路変更届 > 4.2 提出期限\n\n"
    )
    assert result.endswith(element.content)
    assert element.content.startswith("## 4.2")


def test_loads_requested_subset_from_baseline_query_cache(tmp_path) -> None:
    path = tmp_path / "queries.json"
    path.write_text(
        json.dumps(
            {
                "embedding_model": "gemini-embedding-001",
                "questions": ["期限は？", "対象者は？"],
                "vectors": [[0.1, 0.2], [0.3, 0.4]],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    questions = [{"question": "期限は？"}]

    assert load_baseline_query_vectors(path, questions) == {
        "期限は？": [0.1, 0.2]
    }

    with pytest.raises(ValueError, match="評価対象の質問"):
        load_baseline_query_vectors(path, [{"question": "別の質問"}])
