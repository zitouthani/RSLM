import json
import re
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
)

from .qdrant_connection import (
    COLLECTION_NAME,
    replace_document_points,
    _write_embeddings_snapshot,
)


BACKUP_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def _document_backup_dir(backup_root: Path, backup_id: str) -> Path:
    if not BACKUP_ID_PATTERN.fullmatch(backup_id):
        raise ValueError("Identifiant de sauvegarde invalide.")
    return backup_root / "documents" / backup_id


def _document_filter(document: str) -> Filter:
    return Filter(
        must=[
            FieldCondition(
                key="document",
                match=MatchValue(value=document),
            )
        ]
    )


def create_document_backup(
    document_path: Path,
    embeddings_file: Path,
    client: QdrantClient,
    backup_root: Path,
) -> dict[str, Any]:
    document = document_path.name
    backup_id = uuid4().hex
    backup_dir = _document_backup_dir(backup_root, backup_id)
    backup_dir.mkdir(parents=True)
    try:
        existing_embeddings = (
            json.loads(embeddings_file.read_text(encoding="utf-8"))
            if embeddings_file.is_file()
            else []
        )
        document_embeddings = [
            item
            for item in existing_embeddings
            if item.get("document") == document
        ]
        points = []
        if client.collection_exists(COLLECTION_NAME):
            offset = None
            while True:
                records, offset = client.scroll(
                    collection_name=COLLECTION_NAME,
                    scroll_filter=_document_filter(document),
                    limit=128,
                    offset=offset,
                    with_payload=True,
                    with_vectors=True,
                )
                points.extend(
                    {
                        "id": str(record.id),
                        "vector": record.vector,
                        "payload": record.payload or {},
                    }
                    for record in records
                )
                if offset is None:
                    break

        pdf_present = document_path.is_file()
        if pdf_present:
            shutil.copy2(document_path, backup_dir / "document.pdf")
        (backup_dir / "embeddings.json").write_text(
            json.dumps(document_embeddings, ensure_ascii=False),
            encoding="utf-8",
        )
        (backup_dir / "qdrant_points.json").write_text(
            json.dumps(points, ensure_ascii=False),
            encoding="utf-8",
        )
        manifest = {
            "id": backup_id,
            "document": document,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "pdf_present": pdf_present,
            "embedding_chunks": len(document_embeddings),
            "qdrant_points": len(points),
        }
        (backup_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return manifest
    except Exception:
        shutil.rmtree(backup_dir)
        raise


def list_document_backups(
    backup_root: Path,
    document: str | None = None,
) -> list[dict[str, Any]]:
    backup_dir = backup_root / "documents"
    if not backup_dir.is_dir():
        return []
    backups = []
    for manifest_path in backup_dir.glob("*/manifest.json"):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if document is None or manifest["document"] == document:
            backups.append(manifest)
    return sorted(backups, key=lambda item: item["created_at"], reverse=True)


def restore_document_backup(
    backup_id: str,
    document_path: Path,
    embeddings_file: Path,
    client: QdrantClient,
    backup_root: Path,
) -> dict[str, Any]:
    backup_dir = _document_backup_dir(backup_root, backup_id)
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError("Sauvegarde documentaire introuvable.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("document") != document_path.name:
        raise ValueError("La sauvegarde ne correspond pas à ce document.")

    saved_embeddings = json.loads(
        (backup_dir / "embeddings.json").read_text(encoding="utf-8")
    )
    saved_points = json.loads(
        (backup_dir / "qdrant_points.json").read_text(encoding="utf-8")
    )
    saved_pdf = backup_dir / "document.pdf"
    if manifest["pdf_present"] and not saved_pdf.is_file():
        raise FileNotFoundError("Le PDF de cette sauvegarde est absent.")
    points = [
        PointStruct(
            id=item["id"],
            vector=item["vector"],
            payload=item["payload"],
        )
        for item in saved_points
    ]

    replace_document_points(client, document_path.name, points)
    existing_embeddings = (
        json.loads(embeddings_file.read_text(encoding="utf-8"))
        if embeddings_file.is_file()
        else []
    )
    retained = [
        item
        for item in existing_embeddings
        if item.get("document") != document_path.name
    ]
    _write_embeddings_snapshot(embeddings_file, retained + saved_embeddings)

    if manifest["pdf_present"]:
        document_path.parent.mkdir(parents=True, exist_ok=True)
        restore_temp = document_path.with_name(
            f".{document_path.name}.{uuid4().hex}.restore"
        )
        try:
            shutil.copy2(saved_pdf, restore_temp)
            restore_temp.replace(document_path)
        except Exception:
            restore_temp.unlink(missing_ok=True)
            raise
    else:
        document_path.unlink(missing_ok=True)

    return manifest


def create_conversation_backup(
    database_path: Path,
    backup_root: Path,
) -> dict[str, Any]:
    if not database_path.is_file():
        raise FileNotFoundError("La base de conversations n’existe pas encore.")
    backup_id = uuid4().hex
    backup_dir = backup_root / "conversations" / backup_id
    backup_dir.mkdir(parents=True)
    try:
        source = sqlite3.connect(database_path, timeout=10)
        target = sqlite3.connect(backup_dir / "conversations.sqlite3")
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        manifest = {
            "id": backup_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "size_bytes": (backup_dir / "conversations.sqlite3").stat().st_size,
        }
        (backup_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return manifest
    except Exception:
        shutil.rmtree(backup_dir)
        raise


def list_conversation_backups(backup_root: Path) -> list[dict[str, Any]]:
    backup_dir = backup_root / "conversations"
    if not backup_dir.is_dir():
        return []
    backups = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in backup_dir.glob("*/manifest.json")
    ]
    return sorted(backups, key=lambda item: item["created_at"], reverse=True)


def restore_conversation_backup(
    backup_id: str,
    database_path: Path,
    backup_root: Path,
) -> dict[str, Any]:
    if not BACKUP_ID_PATTERN.fullmatch(backup_id):
        raise ValueError("Identifiant de sauvegarde invalide.")
    backup_dir = backup_root / "conversations" / backup_id
    manifest_path = backup_dir / "manifest.json"
    backup_database = backup_dir / "conversations.sqlite3"
    if not manifest_path.is_file() or not backup_database.is_file():
        raise FileNotFoundError("Sauvegarde de conversations introuvable.")

    temporary_database = database_path.with_name(
        f".{database_path.name}.{uuid4().hex}.restore"
    )
    source = sqlite3.connect(backup_database, timeout=10)
    target = sqlite3.connect(temporary_database)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    try:
        temporary_database.replace(database_path)
    except Exception:
        temporary_database.unlink(missing_ok=True)
        raise
    return json.loads(manifest_path.read_text(encoding="utf-8"))
