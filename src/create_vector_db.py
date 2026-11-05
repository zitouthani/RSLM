from pathlib import Path
import json
import os
from uuid import NAMESPACE_URL, uuid5

from qdrant_client.models import PointStruct

from .qdrant_connection import (
    COLLECTION_NAME,
    create_qdrant_client,
    ensure_collection,
    replace_document_points,
)

PROJECT_DIR = Path(__file__).resolve().parent.parent
EMBEDDINGS_FILE = PROJECT_DIR / "data" / "embeddings.json"


def main():

    print("Chargement des embeddings...")

    with open(EMBEDDINGS_FILE, "r", encoding="utf-8") as f:
        embeddings = json.load(f)

    print(f"Embeddings chargés : {len(embeddings)}")

    client = create_qdrant_client()
    ensure_collection(client)
    points_by_document = {}

    for item in embeddings:
        document = item["document"]
        page = item.get("page_start", item["page"])
        chunk_index = item["chunk_index"]
        text = item["text"]
        point_id = str(
            uuid5(
                NAMESPACE_URL,
                f"{document}:{page}:{chunk_index}:{text}",
            )
        )
        point = PointStruct(
            id=point_id,
            vector=item["embedding"],
            payload={
                "document": document,
                "page": page,
                "page_start": page,
                "page_end": item.get("page_end", page),
                "section": item.get("section"),
                "chunk_index": chunk_index,
                "text": text,
            },
        )
        points_by_document.setdefault(document, []).append(point)

    total_points = sum(len(points) for points in points_by_document.values())
    print(f"Synchronisation de {total_points} vecteurs...")
    for document, points in points_by_document.items():
        replace_document_points(client, document, points)

    print("\nBase Qdrant créée avec succès.")

    print(f"Collection : {COLLECTION_NAME}")
    print(f"Nombre de vecteurs : {total_points}")
    print(f"Emplacement : {os.getenv('QDRANT_URL', 'data/qdrant (local)')}")

    client.close()


if __name__ == "__main__":
    main()