from pathlib import Path
import os
from dotenv import load_dotenv


# =========================
# .env の読み込み
# =========================

load_dotenv()


# =========================
# プロジェクト基本パス
# =========================

BASE_DIR = Path(__file__).resolve().parent

DOCS_DIR = BASE_DIR / "docs"
CHROMA_DB_DIR = BASE_DIR / "chroma_db"
LOGS_DIR = BASE_DIR / "logs"

RAG_LOG_PATH = LOGS_DIR / "rag_logs.jsonl"
FEEDBACK_LOG_PATH = LOGS_DIR / "feedback_logs.jsonl"


# =========================
# Gemini API 設定
# =========================

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")

LLM_MODEL_NAME = "gemini-2.5-flash"
EMBEDDING_MODEL_NAME = "gemini-embedding-001"


# =========================
# RAG 検索設定
# =========================

TOP_K = 5

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100


# =========================
# Chroma 設定
# =========================

CHROMA_COLLECTION_NAME = "municipality_rag_docs"


# =========================
# 回答分類
# =========================

ANSWER_TYPE_SUFFICIENT = "根拠十分"
ANSWER_TYPE_NEEDS_JUDGMENT = "判断要"
ANSWER_TYPE_INSUFFICIENT = "文書不足"

ANSWER_TYPES = [
    ANSWER_TYPE_SUFFICIENT,
    ANSWER_TYPE_NEEDS_JUDGMENT,
    ANSWER_TYPE_INSUFFICIENT,
]
