import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

# ============================================================
# CHEMIN DU FICHIER D'AUDIT
# ============================================================

PROJECT_DIR = Path(__file__).resolve().parent.parent

LOG_DIR = PROJECT_DIR / "logs"

AUDIT_FILE = LOG_DIR / "rag_audit.jsonl"


# ============================================================
# CREATION DU DOSSIER LOGS
# ============================================================

def ensure_log_directory() -> None:
    """
    Crée le dossier logs s'il n'existe pas.
    """

    LOG_DIR.mkdir(
        parents=True,
        exist_ok=True
    )


# ============================================================
# IDENTIFIANT UNIQUE DE REQUETE
# ============================================================

def generate_request_id() -> str:
    """
    Génère un identifiant unique pour une requête.
    """

    return str(uuid.uuid4())


# ============================================================
# ECRITURE DU LOG
# ============================================================

def write_audit_log(
    event: dict[str, Any]
) -> None:
    """
    Ajoute un événement dans le fichier JSONL.

    Une requête = une ligne JSON.
    """

    if os.getenv("AUDIT_LOG_ENABLED", "false").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return

    ensure_log_directory()

    print(
        f"📝 AUDIT : écriture dans {AUDIT_FILE}"
    )

    with AUDIT_FILE.open(
        "a",
        encoding="utf-8"
    ) as file:

        json.dump(
            event,
            file,
            ensure_ascii=False
        )

        file.write("\n")

    print(
        "✅ AUDIT : événement enregistré"
    )


# ============================================================
# CREATION D'UN EVENEMENT D'AUDIT
# ============================================================

def create_audit_event(
    question: str,
    status: str = "success",
    request_id: str | None = None,
    sources: list[dict[str, Any]] | None = None,
    best_score: float | None = None,
    results_count: int | None = None,
    reformulation_seconds: float | None = None,
    embedding_seconds: float | None = None,
    qdrant_seconds: float | None = None,
    rerank_seconds: float | None = None,
    context_seconds: float | None = None,
    time_before_ollama_seconds: float | None = None,
    ollama_first_token_seconds: float | None = None,
    ollama_generation_seconds: float | None = None,
    total_seconds: float | None = None,
) -> dict[str, Any]:
    """
    Crée un événement d'audit complet.
    """

    if request_id is None:
        request_id = generate_request_id()

    return {
     "timestamp": datetime.now(
        ZoneInfo("Europe/Paris")
    ).isoformat(),

        "request_id": request_id,

        "question": question,

        "retrieval": {
            "results_count": results_count,
            "best_score": best_score,
            "sources": sources or [],
        },

        "performance": {
            "reformulation_seconds": reformulation_seconds,
            "embedding_seconds": embedding_seconds,
            "qdrant_seconds": qdrant_seconds,
            "rerank_seconds": rerank_seconds,
            "context_seconds": context_seconds,
            "time_before_ollama_seconds": time_before_ollama_seconds,
            "ollama_first_token_seconds": ollama_first_token_seconds,
            "ollama_generation_seconds": ollama_generation_seconds,
            "total_seconds": total_seconds,
        },

        "status": status
    }