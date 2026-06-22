import json
from datetime import datetime
from pathlib import Path

from config import FEEDBACK_LOG_PATH


VALID_FEEDBACK_VALUES = [
    "採用した",
    "修正して採用した",
    "採用しなかった",
]


def save_feedback(
    result: dict,
    feedback: str,
    comment: str = "",
    log_path: Path = FEEDBACK_LOG_PATH,
) -> None:
    """
    RAG回答に対するユーザーフィードバックをJSONL形式で保存する。
    """

    if feedback not in VALID_FEEDBACK_VALUES:
        raise ValueError(
            f"feedback は {VALID_FEEDBACK_VALUES} のいずれかを指定してください。"
        )

    log_path.parent.mkdir(parents=True, exist_ok=True)

    feedback_record = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "question": result["question"],
        "answer": result["answer"],
        "references": result["references"],
        "feedback": feedback,
        "comment": comment,
    }

    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(feedback_record, ensure_ascii=False) + "\n")