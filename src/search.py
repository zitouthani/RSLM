from pathlib import Path

from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer, CrossEncoder


PROJECT_DIR = Path(__file__).resolve().parent.parent

QDRANT_PATH = PROJECT_DIR / "data" / "qdrant"

COLLECTION_NAME = "RSLM_knowledge"

# Modèle utilisé pour la recherche vectorielle
EMBEDDING_MODEL = "BAAI/bge-m3"

# Modèle utilisé pour réordonner les résultats
RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"

# Nombre de candidats récupérés par Qdrant avant reranking
RETRIEVAL_LIMIT = 15

# Nombre de résultats conservés après reranking
FINAL_LIMIT = 5


def main():

    question = input("\nPose ta question : ").strip()

    if not question:
        print("Aucune question fournie.")
        return

    # ---------------------------------------------------------
    # 1. Chargement du modèle d'embeddings
    # ---------------------------------------------------------

    print("\nChargement du modèle d'embeddings...")

    embedding_model = SentenceTransformer(EMBEDDING_MODEL)

    # ---------------------------------------------------------
    # 2. Transformation de la question en embedding
    # ---------------------------------------------------------

    print("Transformation de la question en embedding...")

    question_embedding = embedding_model.encode(
        question,
        normalize_embeddings=True,
    ).tolist()

    # ---------------------------------------------------------
    # 3. Recherche initiale dans Qdrant
    # ---------------------------------------------------------

    client = QdrantClient(path=str(QDRANT_PATH))

    print(
        f"Recherche des {RETRIEVAL_LIMIT} passages "
        "les plus proches..."
    )

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=question_embedding,
        limit=RETRIEVAL_LIMIT,
        with_payload=True,
    )

    candidates = results.points

    if not candidates:
        print("\nAucun passage trouvé.")
        client.close()
        return

    # ---------------------------------------------------------
    # 4. Chargement du reranker
    # ---------------------------------------------------------

    print("\nChargement du reranker...")

    reranker = CrossEncoder(RERANKER_MODEL)

    # ---------------------------------------------------------
    # 5. Création des paires question / passage
    # ---------------------------------------------------------

    pairs = [
        [question, result.payload["text"]]
        for result in candidates
    ]

    print("Calcul des scores de reranking...")

    reranker_scores = reranker.predict(pairs)

    # ---------------------------------------------------------
    # 6. Associer chaque score au passage correspondant
    # ---------------------------------------------------------

    ranked_results = []

    for result, reranker_score in zip(candidates, reranker_scores):

        ranked_results.append(
            {
                "result": result,
                "reranker_score": float(reranker_score),
            }
        )

    # Tri du meilleur au moins bon
    ranked_results.sort(
        key=lambda x: x["reranker_score"],
        reverse=True,
    )

    # ---------------------------------------------------------
    # 7. Affichage des meilleurs résultats
    # ---------------------------------------------------------

    print("\n" + "=" * 70)
    print("RÉSULTATS APRÈS RERANKING")
    print("=" * 70)

    for i, item in enumerate(
        ranked_results[:FINAL_LIMIT],
        start=1,
    ):

        result = item["result"]
        reranker_score = item["reranker_score"]

        print(f"\nRésultat #{i}")
        print("-" * 70)

        print(f"Score Qdrant      : {result.score:.4f}")
        print(f"Score Reranker    : {reranker_score:.4f}")
        print(f"Document          : {result.payload['document']}")
        print(f"Page              : {result.payload['page']}")
        print(f"Chunk             : {result.id}")

        if result.payload.get("section"):
            print(f"Section           : {result.payload['section']}")

        print("\nTexte :")
        print(result.payload["text"])

    client.close()


if __name__ == "__main__":
    main()