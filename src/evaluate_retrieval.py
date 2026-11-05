import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

import numpy as np
from dotenv import load_dotenv
from sentence_transformers import CrossEncoder, SentenceTransformer

from .console import configure_console_encoding
from .retrieval import apply_document_exclusions, parse_excluded_documents


configure_console_encoding()
PROJECT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_DIR / ".env")
EMBEDDINGS_FILE = PROJECT_DIR / "data" / "embeddings.json"
BENCHMARK_FILE = PROJECT_DIR / "data" / "retrieval_eval.json"
EMBEDDING_MODEL = "BAAI/bge-m3"
RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"


def source_matches(
    result: dict[str, Any],
    expected_sources: list[dict[str, Any]],
) -> bool:
    page = result.get("page_start", result.get("page", 0))
    return any(
        result.get("document") == source["document"]
        and source["page_start"] <= page <= source["page_end"]
        for source in expected_sources
    )


def reciprocal_rank(
    results: list[dict[str, Any]],
    expected_sources: list[dict[str, Any]],
) -> float:
    for rank, result in enumerate(results, start=1):
        if source_matches(result, expected_sources):
            return 1.0 / rank
    return 0.0


def evaluate(top_k: int, output: Path | None) -> dict[str, Any]:
    chunks = json.loads(EMBEDDINGS_FILE.read_text(encoding="utf-8"))
    benchmark = json.loads(BENCHMARK_FILE.read_text(encoding="utf-8"))
    excluded = parse_excluded_documents(os.getenv("RAG_EXCLUDED_DOCUMENTS"))
    chunks = apply_document_exclusions(chunks, excluded)
    vectors = np.asarray([chunk["embedding"] for chunk in chunks], dtype=np.float32)

    embedding_model = SentenceTransformer(EMBEDDING_MODEL)
    reranker = CrossEncoder(RERANKER_MODEL)
    report = []
    retrieval_hits = 0
    reranked_hits = 0
    retrieval_rr = []
    reranked_rr = []
    started = time.perf_counter()

    for sample in benchmark:
        query_vector = embedding_model.encode(
            sample["question"],
            normalize_embeddings=True,
        )
        scores = vectors @ query_vector
        order = np.argsort(scores)[::-1]
        candidate_scores = [
            (chunks[int(index)], float(scores[index]))
            for index in order[:top_k]
        ]
        candidates = [item for item, _ in candidate_scores]
        ranked = reranker.predict(
            [[sample["question"], item["text"]] for item in candidates],
            batch_size=8,
            show_progress_bar=False,
        )
        reranked_scores = sorted(
            (
                (item, float(score))
                for item, score in zip(candidates, ranked)
            ),
            key=lambda pair: pair[1],
            reverse=True,
        )
        reranked = [item for item, _ in reranked_scores]
        expected = sample["expected_sources"]
        raw_rr = reciprocal_rank(candidates, expected)
        reranked_mrr = reciprocal_rank(reranked, expected)
        raw_hit = raw_rr > 0
        reranked_hit = any(
            source_matches(item, expected)
            for item in reranked[:3]
        )
        retrieval_hits += raw_hit
        reranked_hits += reranked_hit
        retrieval_rr.append(raw_rr)
        reranked_rr.append(reranked_mrr)
        report.append(
            {
                "id": sample["id"],
                "question": sample["question"],
                "expected_sources": expected,
                "retrieval_hit_at_k": raw_hit,
                "retrieval_reciprocal_rank": raw_rr,
                "reranked_hit_at_3": reranked_hit,
                "reranked_reciprocal_rank": reranked_mrr,
                "top_retrieved": [
                    {
                        "document": item["document"],
                        "page": item.get("page_start", item.get("page")),
                        "score": round(score, 4),
                    }
                    for item, score in candidate_scores[:3]
                ],
                "top_reranked": [
                    {
                        "document": item["document"],
                        "page": item.get("page_start", item.get("page")),
                        "reranker_score": round(score, 4),
                    }
                    for item, score in reranked_scores[:3]
                ],
            }
        )

    result = {
        "benchmark": str(BENCHMARK_FILE.name),
        "embedding_model": EMBEDDING_MODEL,
        "reranker_model": RERANKER_MODEL,
        "top_k": top_k,
        "excluded_documents": sorted(excluded),
        "sample_count": len(benchmark),
        "retrieval_hit_at_k": retrieval_hits / len(benchmark),
        "retrieval_mrr_at_k": sum(retrieval_rr) / len(benchmark),
        "reranked_hit_at_3": reranked_hits / len(benchmark),
        "reranked_mrr_at_k": sum(reranked_rr) / len(benchmark),
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "queries": report,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Évalue la recherche vectorielle RSLM avec un jeu de questions de référence."
    )
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_DIR / "logs" / "retrieval_eval_latest.json",
    )
    args = parser.parse_args()
    if args.top_k < 3:
        parser.error("--top-k doit être au moins égal à 3.")
    evaluate(args.top_k, args.output)


if __name__ == "__main__":
    main()
