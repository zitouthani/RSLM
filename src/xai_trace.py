import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent.parent
XAI_TRACE_FILE = PROJECT_DIR / "logs" / "xai_trace.jsonl"
_TRACE_LOCK = threading.Lock()


def build_retrieval_graph(trace: dict[str, Any]) -> dict[str, Any]:
    guardrail = trace.get("guardrail", {})
    ranked = {
        item["candidate_id"]: item
        for item in trace.get("reranked_candidates", [])
    }
    selected = {
        item["candidate_id"]: item
        for item in trace.get("selected_context", [])
    }
    excluded = {
        item["candidate_id"]
        for item in trace.get("excluded_candidates", [])
    }
    reranker_used = trace.get("reranker_used", False)
    candidates = []
    excluded_count = 0
    withheld_count = 0
    for item in trace.get("retrieval_path", []):
        candidate_id = item["candidate_id"]
        ranking = ranked.get(candidate_id)
        if candidate_id in excluded:
            excluded_count += 1
            continue
        if guardrail.get("allowed") is not True:
            withheld_count += 1
            continue
        if candidate_id in selected:
            reason = "selected"
        elif ranking and ranking["rank"] <= trace.get("final_limit", 0):
            reason = "context_limit"
        else:
            reason = "rank_limit"
        candidates.append({
            "id": candidate_id,
            "document": item["document"],
            "page": item["page"],
            "preview": selected[candidate_id]["text"] if candidate_id in selected else item.get("text_preview", ""),
            "vector_rank": item["rank"],
            "vector_score": item["vector_score"],
            "rerank_rank": ranking["rank"] if ranking else None,
            "reranker_score": ranking["reranker_score"] if ranking and reranker_used else None,
            "reason": reason,
        })
    return {
        "question": trace.get("question", ""),
        "search_query": trace.get("search_query"),
        "question_terms": guardrail.get("question_terms", []),
        "shared_terms": guardrail.get("shared_terms", []),
        "guardrail_allowed": guardrail.get("allowed"),
        "best_vector_score": guardrail.get("best_vector_score"),
        "minimum_vector_score": guardrail.get("minimum_vector_score"),
        "reranker_used": reranker_used,
        "final_limit": trace.get("final_limit"),
        "excluded_count": excluded_count,
        "withheld_count": withheld_count,
        "candidates": candidates,
    }


def retrieval_graph_mermaid(graph: dict[str, Any]) -> str:
    lines = ['flowchart TD', 'question["Question"]']
    if not graph.get("search_query"):
        lines.append('question --> answer["Réponse directe"]')
        return "\n".join(lines)
    lines.extend([
        'question --> query["Requête de recherche"]',
        'query --> search["Recherche vectorielle et classement"]',
    ])
    for index, candidate in enumerate(graph.get("candidates", []), start=1):
        status = "Retenu" if candidate.get("reason") == "selected" else "Non retenu"
        lines.append(f' search --> candidate{index}["Passage {index} : {status}"]')
        if candidate.get("reason") == "selected":
            lines.append(f' candidate{index} --> context["Contexte transmis"]')
    lines.append('search --> check["Contrôle de pertinence"]')
    if graph.get("guardrail_allowed") is True:
        lines.append('check -->|"Contrôle lexical"| context["Contexte transmis"]')
        lines.append('context --> answer["Réponse"]')
    else:
        lines.append('check --> answer["Réponse sans contexte"]')
    return "\n".join(lines)


def citation_provenance(
    sources: list[dict[str, Any]],
    context_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    context_source_keys = {
        (item["document"], str(item["page"]))
        for item in context_items
    }
    return [
        {
            "document": source["document"],
            "page": source["page"],
            "available_in_model_context": (
                source["document"],
                str(source["page"]),
            ) in context_source_keys,
        }
        for source in sources
    ]


def write_xai_trace(
    trace: dict[str, Any] | None,
    status: str,
    answer: str | None = None,
    error: str | None = None,
) -> None:
    if os.getenv("XAI_TRACE_ENABLED", "false").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return
    if trace is None:
        return
    event = {
        **trace,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "answer": answer,
        "error": error,
    }
    XAI_TRACE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _TRACE_LOCK:
        with XAI_TRACE_FILE.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")
