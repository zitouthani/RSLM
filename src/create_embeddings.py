from pathlib import Path
import json

from sentence_transformers import SentenceTransformer


PROJECT_DIR = Path(__file__).resolve().parent.parent

INPUT_FILE = PROJECT_DIR / "data" / "chunks.json"
OUTPUT_FILE = PROJECT_DIR / "data" / "embeddings.json"

MODEL_NAME = "BAAI/bge-m3"


def main():

    print("Chargement du modèle d'embeddings...")
    print(f"Modèle : {MODEL_NAME}")

    model = SentenceTransformer(MODEL_NAME)

    print("Modèle chargé.\n")

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    texts = [chunk["text"] for chunk in chunks]

    print(f"Nombre de chunks : {len(texts)}")
    print("Création des embeddings...")

    embeddings = model.encode(
        texts,
        batch_size=8,
        show_progress_bar=True,
        normalize_embeddings=True,
    )

    results = []

    for chunk, embedding in zip(chunks, embeddings):

        results.append(
            {
                "chunk_id": chunk["chunk_id"],
                "document": chunk["document"],
                "page": chunk["page"],
                "page_start": chunk["page_start"],
                "page_end": chunk["page_end"],
                "section": chunk["section"],
                "chunk_index": chunk["chunk_index"],
                "text": chunk["text"],
                "embedding": embedding.tolist(),
            }
        )

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:

        json.dump(
            results,
            f,
            ensure_ascii=False,
        )

    print("\nTerminé.")
    print(f"Embeddings créés : {len(results)}")
    print(f"Fichier : {OUTPUT_FILE}")


if __name__ == "__main__":
    main()