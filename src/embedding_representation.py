"""Text representations used only to create retrieval vectors."""

from __future__ import annotations

from src.contracts import IndexableElement


HEADING_KEYS = ("見出し1", "見出し2", "見出し3")


def contextual_heading_document_text(element: IndexableElement) -> str:
    """Add document and heading context without mutating the stored content."""
    heading = " > ".join(
        str(element.metadata[key])
        for key in HEADING_KEYS
        if element.metadata.get(key)
    )
    context = [f"文書: {element.document_name}"]
    if heading:
        context.append(f"見出し: {heading}")
    return "\n".join(context) + f"\n\n{element.content}"
