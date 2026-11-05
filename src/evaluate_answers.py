import argparse
import json
import os
import re
import time
import unicodedata
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from .console import configure_console_encoding


configure_console_encoding()
PROJECT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_DIR / ".env")
BENCHMARK_FILE = PROJECT_DIR / "data" / "answer_eval.json"


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )
    return " ".join(re.findall(r"[a-z0-9]+", without_accents))


def evaluate_answer(
    answer: str,
    sources: list[dict[str, Any]],
    expected_facts: list[dict[str, Any]],
    expected_sources: list[dict[str, Any]],
) -> dict[str, Any]:
    normalized_answer = normalize_text(answer)
    facts = [
        {
            "label": fact["label"],
            "present": any(
                normalize_text(term) in normalized_answer
                for term in fact["any_terms"]
            ),
        }
        for fact in expected_facts
    ]
    cited_expected_source = any(
        expected["page_start"]
        <= source.get("page", source.get("page_start", 0))
        <= expected["page_end"]
        and source.get("document") == expected["document"]
        for expected in expected_sources
        for source in sources
    )

    fact_coverage = (
        sum(fact["present"] for fact in facts) / len(facts)
        if facts
        else 1.0
    )
    source_coverage = float(cited_expected_source) if expected_sources else 1.0
    return {
        "expected_facts": facts,
        "fact_coverage": fact_coverage,
        "expected_source_cited": cited_expected_source,
        "source_coverage": source_coverage,
        "passes_lexical_checks": (
            all(fact["present"] for fact in facts)
            and cited_expected_source
        ),
    }


def evaluate(api_url: str, timeout: int, output: Path | None) -> dict[str, Any]:
    benchmark = json.loads(BENCHMARK_FILE.read_text(encoding="utf-8"))
    results = []
    started = time.perf_counter()
    for sample in benchmark:
        response = requests.post(
            f"{api_url.rstrip('/')}/chat",
            json={"question": sample["question"], "historique": []},
            timeout=timeout,
        )
        response.raise_for_status()
        generated = response.json()
        evaluation = evaluate_answer(
            generated.get("reponse", ""),
            generated.get("sources", []),
            sample["expected_facts"],
            sample["expected_sources"],
        )
        results.append(
            {
                "id": sample["id"],
                "question": sample["question"],
                "answer": generated.get("reponse", ""),
                "sources": generated.get("sources", []),
                **evaluation,
            }
        )

    result = {
        "benchmark": BENCHMARK_FILE.name,
        "api_url": api_url.rstrip("/"),
        "sample_count": len(results),
        "mean_fact_coverage": sum(
            item["fact_coverage"] for item in results
        ) / len(results),
        "expected_source_coverage": sum(
            item["source_coverage"] for item in results
        ) / len(results),
        "lexical_pass_rate": sum(
            item["passes_lexical_checks"] for item in results
        ) / len(results),
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "evaluation_note": (
            "Les faits sont vérifiés par présence de termes annotés et les "
            "sources par document/page. Ces indicateurs facilitent la "
            "régression, mais ne remplacent pas une validation humaine."
        ),
        "queries": results,
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
        description="Évalue les réponses RSLM avec des faits et sources annotés."
    )
    parser.add_argument(
        "--api-url",
        default=os.getenv("RSLM_API_URL", "http://127.0.0.1:8080"),
    )
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_DIR / "logs" / "answer_eval_latest.json",
    )
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error("--timeout doit être positif.")
    evaluate(args.api_url, args.timeout, args.output)


if __name__ == "__main__":
    main()
