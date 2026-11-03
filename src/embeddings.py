from langchain_google_genai import GoogleGenerativeAIEmbeddings

from config import GOOGLE_API_KEY, EMBEDDING_MODEL_NAME
from src.smoke_context import remaining_seconds


def get_embeddings() -> GoogleGenerativeAIEmbeddings:
    """
    Gemini の Embedding モデルを生成する。
    """

    if not GOOGLE_API_KEY:
        raise ValueError(
            "GOOGLE_API_KEY が設定されていません。"
            ".env ファイルに GOOGLE_API_KEY を設定してください。"
        )

    timeout = remaining_seconds()
    options = {"client_args": {"timeout": timeout}} if timeout is not None else {}
    embeddings = GoogleGenerativeAIEmbeddings(
        model=EMBEDDING_MODEL_NAME,
        google_api_key=GOOGLE_API_KEY,
        **options,
    )

    return embeddings


# if __name__ == "__main__":
#     embeddings = get_embeddings()

#     text = "扶養手当の支給要件を確認したい。"
#     vector = embeddings.embed_query(text)

#     print(f"ベクトルの次元数: {len(vector)}")
#     print(vector[:5])
