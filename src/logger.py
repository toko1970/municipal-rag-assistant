import json
from datetime import datetime
from pathlib import Path

from config import RAG_LOG_PATH


def save_rag_log(result: dict, log_path: Path = RAG_LOG_PATH) -> None:
    """
    RAGの実行結果をJSONL形式で保存する。
    """

    log_path.parent.mkdir(parents=True, exist_ok=True)

    log_record = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "question": result["question"],
        "answer": result["answer"],
        "references": result["references"],
    }

    with log_path.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(log_record, ensure_ascii=False) + "\n"
        )