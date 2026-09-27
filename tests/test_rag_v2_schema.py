from src.persistence.models import Base


def test_required_rag_v2_tables_are_declared() -> None:
    assert set(Base.metadata.tables) == {
        "documents",
        "document_versions",
        "content_elements",
        "visual_assets",
        "embedding_profiles",
        "rag_requests",
        "retrieval_results",
        "generation_results",
        "generation_attempts",
        "classification_attempts",
        "answer_claims",
        "claim_evidence",
        "feedback",
    }
