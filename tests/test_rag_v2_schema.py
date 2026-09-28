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


def test_visual_asset_uses_backend_neutral_storage_uri() -> None:
    columns = Base.metadata.tables["visual_assets"].columns

    assert "storage_uri" in columns
    assert "local_path" not in columns
