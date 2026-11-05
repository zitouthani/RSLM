import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


PROJECT_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_DIR / "data" / "conversations.sqlite3"


def _connect() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            messages_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    return connection


@contextmanager
def _connection() -> Iterator[sqlite3.Connection]:
    connection = _connect()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def list_conversations() -> list[dict[str, Any]]:
    with _connection() as connection:
        rows = connection.execute(
            "SELECT id, title, updated_at FROM conversations "
            "ORDER BY updated_at DESC"
        ).fetchall()
    return [
        {"id": row[0], "title": row[1], "updated_at": row[2]}
        for row in rows
    ]


def load_conversation(conversation_id: int) -> list[dict[str, Any]]:
    with _connection() as connection:
        row = connection.execute(
            "SELECT messages_json FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
    if row is None:
        return []
    return json.loads(row[0])


def save_conversation(
    conversation_id: int | None,
    messages: list[dict[str, Any]],
) -> int:
    first_question = next(
        (
            message["content"].strip()
            for message in messages
            if message.get("role") == "user"
        ),
        "Nouvelle conversation",
    )
    title = first_question[:72] + ("..." if len(first_question) > 72 else "")
    serialized = json.dumps(messages, ensure_ascii=False)
    updated_at = datetime.now(timezone.utc).isoformat()

    with _connection() as connection:
        if conversation_id is None:
            cursor = connection.execute(
                "INSERT INTO conversations "
                "(title, messages_json, updated_at) VALUES (?, ?, ?)",
                (title, serialized, updated_at),
            )
            return int(cursor.lastrowid)

        connection.execute(
            "UPDATE conversations SET title = ?, messages_json = ?, "
            "updated_at = ? WHERE id = ?",
            (title, serialized, updated_at, conversation_id),
        )
        return conversation_id


def delete_conversation(conversation_id: int) -> None:
    with _connection() as connection:
        connection.execute(
            "DELETE FROM conversations WHERE id = ?",
            (conversation_id,),
        )
