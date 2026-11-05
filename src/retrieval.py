from collections.abc import Iterable
from typing import Any


def parse_excluded_documents(value: str | None) -> set[str]:
    return {
        document.strip()
        for document in (value or "").split(",")
        if document.strip()
    }


def apply_document_exclusions(
    candidates: Iterable[Any],
    excluded_documents: set[str],
) -> list[Any]:
    def document_name(candidate: Any) -> str | None:
        payload = (
            candidate.get("payload", candidate)
            if isinstance(candidate, dict)
            else candidate.payload
        )
        return payload.get("document")

    return [
        candidate
        for candidate in candidates
        if document_name(candidate) not in excluded_documents
    ]
