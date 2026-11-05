import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent.parent
XAI_TRACE_FILE = PROJECT_DIR / "logs" / "xai_trace.jsonl"
_TRACE_LOCK = threading.Lock()


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
