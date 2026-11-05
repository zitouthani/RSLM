from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from pypdf import PdfReader
from qdrant_client.models import PointStruct
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient

from .create_chunks import (
    detect_running_headers_footers,
    split_into_sections,
    split_section_text,
)
from .qdrant_connection import (
    replace_document_embeddings,
    replace_document_points,
)


def index_pdf(
    pdf_path: Path,
    embedding_model: SentenceTransformer,
    client: QdrantClient,
) -> int:
    pages = []
    reader = PdfReader(pdf_path)
    for page_number, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append(
                {
                    "document": pdf_path.name,
                    "page": page_number,
                    "text": text,
                }
            )

    if not pages:
        raise ValueError("Le PDF ne contient aucun texte exploitable.")

    headers_footers = detect_running_headers_footers(pages)
    sections = split_into_sections(pages, headers_footers)
    chunks = []

    for section in sections:
        for index, text in enumerate(split_section_text(section["text"])):
            if index > 0 and section["title"]:
                text = f"[{section['title']}]\n\n{text}"
            chunks.append(
                {
                    "text": text,
                    "page": section["page_start"],
                    "page_start": section["page_start"],
                    "page_end": section["page_end"],
                    "section": section["title"],
                    "chunk_index": index,
                }
            )

    if not chunks:
        raise ValueError("Aucun passage n’a pu être extrait du PDF.")

    vectors = embedding_model.encode(
        [chunk["text"] for chunk in chunks],
        batch_size=8,
        normalize_embeddings=True,
        show_progress_bar=False,
    )

    points = []
    for chunk, vector in zip(chunks, vectors):
        point_id = str(
            uuid5(
                NAMESPACE_URL,
                f"{pdf_path.name}:{chunk['page_start']}:{chunk['chunk_index']}:{chunk['text']}",
            )
        )
        points.append(
            PointStruct(
                id=point_id,
                vector=vector.tolist(),
                payload={
                    "document": pdf_path.name,
                    "page": chunk["page"],
                    "page_start": chunk["page_start"],
                    "page_end": chunk["page_end"],
                    "section": chunk["section"],
                    "chunk_index": chunk["chunk_index"],
                    "text": chunk["text"],
                },
            )
        )

    replace_document_points(client, pdf_path.name, points)
    replace_document_embeddings(
        Path(__file__).resolve().parent.parent / "data" / "embeddings.json",
        pdf_path.name,
        points,
    )
    return len(points)
