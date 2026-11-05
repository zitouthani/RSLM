import os
import json
from pathlib import Path

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)


PROJECT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_DIR / ".env")
QDRANT_PATH = PROJECT_DIR / "data" / "qdrant"
COLLECTION_NAME = "RSLM_knowledge"
VECTOR_SIZE = 1024


def create_qdrant_client() -> QdrantClient:
    url = os.getenv("QDRANT_URL", "").strip()
    if url:
        return QdrantClient(url=url)
    return QdrantClient(path=str(QDRANT_PATH))


def ensure_collection(client: QdrantClient) -> None:
    if not client.collection_exists(COLLECTION_NAME):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=VECTOR_SIZE,
                distance=Distance.COSINE,
            ),
        )


def initialize_collection(
    client: QdrantClient,
    embeddings_file: Path,
) -> None:
    if client.collection_exists(COLLECTION_NAME):
        return

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(
            size=VECTOR_SIZE,
            distance=Distance.COSINE,
        ),
    )

    if not embeddings_file.is_file():
        print(
            "Aucun corpus initial : Qdrant est prêt avec une collection vide. "
            "Ajoutez des PDF depuis l’interface d’administration."
        )
        return

    with embeddings_file.open("r", encoding="utf-8") as file:
        embeddings = json.load(file)
    if not embeddings:
        client.delete_collection(COLLECTION_NAME)
        raise ValueError("Le fichier d’embeddings ne contient aucun passage.")

    try:
        for start in range(0, len(embeddings), 128):
            points = [
                PointStruct(
                    id=item["chunk_id"],
                    vector=item["embedding"],
                    payload={
                        "document": item["document"],
                        "page": item["page"],
                        "page_start": item.get("page_start", item["page"]),
                        "page_end": item.get("page_end", item["page"]),
                        "section": item.get("section", ""),
                        "chunk_index": item["chunk_index"],
                        "text": item["text"],
                    },
                )
                for item in embeddings[start:start + 128]
            ]
            if points:
                client.upsert(
                    collection_name=COLLECTION_NAME,
                    points=points,
                    wait=True,
                )
    except Exception as error:
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception as cleanup_error:
            raise RuntimeError(
                "Le chargement initial de Qdrant a échoué et la collection "
                f"partielle n’a pas pu être supprimée : {cleanup_error}"
            ) from error
        raise


def replace_document_points(
    client: QdrantClient,
    document: str,
    points: list[PointStruct],
) -> None:
    ensure_collection(client)
    new_ids = {str(point.id) for point in points}

    if points:
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=points,
            wait=True,
        )

    old_ids = []
    offset = None
    document_filter = Filter(
        must=[
            FieldCondition(
                key="document",
                match=MatchValue(value=document),
            )
        ]
    )

    while True:
        records, offset = client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=document_filter,
            limit=256,
            offset=offset,
            with_payload=False,
            with_vectors=False,
        )
        old_ids.extend(
            record.id
            for record in records
            if str(record.id) not in new_ids
        )
        if offset is None:
            break

    if old_ids:
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=old_ids,
            wait=True,
        )


def count_document_points(client: QdrantClient) -> dict[str, int]:
    if not client.collection_exists(COLLECTION_NAME):
        return {}

    counts: dict[str, int] = {}
    offset = None
    while True:
        records, offset = client.scroll(
            collection_name=COLLECTION_NAME,
            limit=256,
            offset=offset,
            with_payload=["document"],
            with_vectors=False,
        )
        for record in records:
            document = (record.payload or {}).get("document")
            if document:
                counts[document] = counts.get(document, 0) + 1
        if offset is None:
            return counts


def delete_document_points(client: QdrantClient, document: str) -> int:
    if not client.collection_exists(COLLECTION_NAME):
        return 0

    document_filter = Filter(
        must=[
            FieldCondition(
                key="document",
                match=MatchValue(value=document),
            )
        ]
    )
    count = client.count(
        collection_name=COLLECTION_NAME,
        count_filter=document_filter,
        exact=True,
    ).count
    if count:
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=document_filter,
            wait=True,
        )
    return count


def replace_document_embeddings(
    embeddings_file: Path,
    document: str,
    points: list[PointStruct],
) -> int:
    existing = (
        json.loads(embeddings_file.read_text(encoding="utf-8"))
        if embeddings_file.is_file()
        else []
    )
    retained = [
        item for item in existing
        if item.get("document") != document
    ]
    replacement = [
        {
            "chunk_id": point.id,
            "document": document,
            "page": point.payload["page"],
            "page_start": point.payload["page_start"],
            "page_end": point.payload["page_end"],
            "section": point.payload["section"],
            "chunk_index": point.payload["chunk_index"],
            "text": point.payload["text"],
            "embedding": point.vector,
        }
        for point in points
    ]
    _write_embeddings_snapshot(embeddings_file, retained + replacement)
    return len(replacement)


def remove_document_embeddings(embeddings_file: Path, document: str) -> int:
    if not embeddings_file.is_file():
        return 0
    existing = json.loads(embeddings_file.read_text(encoding="utf-8"))
    retained = [
        item for item in existing
        if item.get("document") != document
    ]
    removed_count = len(existing) - len(retained)
    if removed_count:
        _write_embeddings_snapshot(embeddings_file, retained)
    return removed_count


def _write_embeddings_snapshot(embeddings_file: Path, data: list[dict]) -> None:
    embeddings_file.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = embeddings_file.with_name(
        f".{embeddings_file.name}.tmp"
    )
    temporary_file.write_text(
        json.dumps(data, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary_file.replace(embeddings_file)
