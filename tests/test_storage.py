import json
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
from streamlit.testing.v1 import AppTest

from src import chat_store
from src.audit_logger import write_audit_log
from src.backup_store import (
    create_conversation_backup,
    create_document_backup,
    restore_conversation_backup,
    restore_document_backup,
)
from src.qdrant_connection import (
    COLLECTION_NAME,
    count_document_points,
    delete_document_points,
    initialize_collection,
    remove_document_embeddings,
    replace_document_embeddings,
    replace_document_points,
)
from src.retrieval import apply_document_exclusions, parse_excluded_documents
from src.evaluate_retrieval import reciprocal_rank, source_matches
from src.evaluate_answers import evaluate_answer
from src.xai_trace import build_retrieval_graph, citation_provenance, retrieval_graph_mermaid, write_xai_trace


class RetrievalGraphTests(unittest.TestCase):
    def test_streamlit_displays_graph_from_a_synthetic_conversation(self):
        graph = {
            "question": "Question fictive", "search_query": "tri",
            "question_terms": ["tri"], "shared_terms": ["tri"],
            "guardrail_allowed": True,
            "candidates": [{"id": "1", "document": "guide.pdf", "page": 2, "vector_rank": 1, "vector_score": 0.8, "rerank_rank": 1, "reranker_score": 0.9, "reason": "selected", "preview": "Passage fictif"}],
        }
        with tempfile.TemporaryDirectory() as directory, patch.object(chat_store, "DATABASE_PATH", Path(directory) / "test.sqlite3"), patch("dotenv.load_dotenv", return_value=False):
            app = AppTest.from_file(str(Path(__file__).resolve().parent.parent / "src" / "app_stream.py"), default_timeout=30)
            app.session_state["messages"] = [{"role": "assistant", "content": "Réponse fictive", "retrieval_graph": graph, "sources": [{"document": "guide.pdf", "page": 2, "extrait": "tSortRow\nPassage fictif"}]}]
            app.run()
            self.assertFalse(app.exception)
            self.assertTrue(any(element.label == "Graphe de recherche" for element in app.expander))
            self.assertTrue(any("flowchart TD" in element.value for element in app.markdown))
            self.assertTrue(any("Passage 1" in element.value for element in app.text))
            self.assertTrue(any(element.value == "tSortRow\nPassage fictif" for element in app.text))
            refused_graph = {**graph, "guardrail_allowed": False, "missing_identifiers": ["tsortrow"], "candidates": []}
            app.session_state["messages"] = [{"role": "assistant", "content": "Réponse refusée", "retrieval_graph": refused_graph}]
            app.run()
            self.assertFalse(app.exception)
            self.assertTrue(any("Identifiants absents du contexte : tsortrow" == element.value for element in app.text))

    def test_mermaid_does_not_interpret_document_or_question_as_diagram_code(self):
        graph = {
            "question": 'secret"] --> injected["bad',
            "search_query": "trier",
            "guardrail_allowed": True,
            "candidates": [{"document": 'secret"] --> injected["bad', "reason": "selected"}, {"reason": "rank_limit"}],
        }
        diagram = retrieval_graph_mermaid(graph)
        self.assertIn('candidate1["Passage 1 : Retenu"]', diagram)
        self.assertIn('candidate1 --> context', diagram)
        self.assertNotIn('candidate2 --> context', diagram)
        self.assertNotIn("secret", diagram)
        self.assertNotIn("injected", diagram)

    def test_graph_distinguishes_candidates_and_reports_real_selection(self):
        trace = {
            "question": "Comment trier ?",
            "search_query": "Comment trier ?",
            "retrieval_path": [
                {"candidate_id": "a", "rank": 1, "document": "guide.pdf", "page": 2, "vector_score": 0.9, "text_preview": "Extrait A"},
                {"candidate_id": "b", "rank": 2, "document": "guide.pdf", "page": 2, "vector_score": 0.8, "text_preview": "Extrait B"},
                {"candidate_id": "c", "rank": 3, "document": "autre.pdf", "page": 1, "vector_score": 0.7, "text_preview": "Extrait C"},
            ],
            "excluded_candidates": [{"candidate_id": "c"}],
            "reranked_candidates": [
                {"candidate_id": "b", "rank": 1, "reranker_score": 0.6},
                {"candidate_id": "a", "rank": 2, "reranker_score": 0.4},
            ],
            "selected_context": [{"candidate_id": "b", "text": "Passage transmis B"}],
            "guardrail": {"allowed": True, "question_terms": ["trier"], "shared_terms": ["trier"]},
            "reranker_used": True,
            "final_limit": 1,
            "conversation_history": [{"content": "do not include"}],
        }
        graph = build_retrieval_graph(trace)
        self.assertEqual([item["reason"] for item in graph["candidates"]], ["rank_limit", "selected"])
        self.assertEqual(graph["excluded_count"], 1)
        self.assertNotIn("autre.pdf", json.dumps(graph))
        self.assertEqual(graph["candidates"][1]["reranker_score"], 0.6)
        self.assertEqual(graph["candidates"][1]["preview"], "Passage transmis B")
        self.assertNotIn("conversation_history", graph)

    def test_graph_marks_blocked_candidates_and_vector_fallback(self):
        trace = {
            "retrieval_path": [{"candidate_id": "a", "rank": 1, "document": "guide.pdf", "page": 1, "vector_score": 0.4}],
            "reranked_candidates": [{"candidate_id": "a", "rank": 1, "reranker_score": 0.4}],
            "guardrail": {"allowed": False},
            "reranker_used": False,
            "final_limit": 3,
        }
        graph = build_retrieval_graph(trace)
        self.assertEqual(graph["candidates"], [])
        self.assertEqual(graph["withheld_count"], 1)
        self.assertNotIn("guide.pdf", json.dumps(graph))

    def test_graph_does_not_label_vector_fallback_as_reranker_score(self):
        trace = {
            "retrieval_path": [{"candidate_id": "a", "rank": 1, "document": "guide.pdf", "page": 1, "vector_score": 0.7}],
            "reranked_candidates": [{"candidate_id": "a", "rank": 1, "reranker_score": 0.7}],
            "guardrail": {"allowed": True},
            "reranker_used": False,
            "final_limit": 3,
        }
        self.assertIsNone(build_retrieval_graph(trace)["candidates"][0]["reranker_score"])


class ChatStoreTests(unittest.TestCase):
    def test_conversations_can_be_saved_loaded_and_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "conversations.sqlite3"
            with patch.object(chat_store, "DATABASE_PATH", database):
                messages = [
                    {"role": "user", "content": "Question de test"},
                    {
                        "role": "assistant",
                        "content": "Réponse",
                        "sources": [],
                    },
                ]

                conversation_id = chat_store.save_conversation(None, messages)
                self.assertEqual(chat_store.load_conversation(conversation_id), messages)
                self.assertEqual(len(chat_store.list_conversations()), 1)

                chat_store.delete_conversation(conversation_id)
                self.assertEqual(chat_store.list_conversations(), [])


class QdrantSyncTests(unittest.TestCase):
    def test_missing_embeddings_create_an_empty_collection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = QdrantClient(path=str(root / "qdrant"))
            try:
                initialize_collection(client, root / "missing_embeddings.json")
                self.assertTrue(client.collection_exists(COLLECTION_NAME))
                records, _ = client.scroll(
                    collection_name=COLLECTION_NAME,
                    limit=10,
                    with_payload=False,
                )
                self.assertEqual(records, [])
            finally:
                client.close()

    def test_new_collection_is_seeded_from_embeddings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            embeddings_file = root / "embeddings.json"
            embeddings_file.write_text(
                json.dumps(
                    [
                        {
                            "chunk_id": 1,
                            "document": "guide.pdf",
                            "page": 1,
                            "chunk_index": 0,
                            "text": "Passage de test",
                            "embedding": [1.0] + [0.0] * 1023,
                        }
                    ]
                ),
                encoding="utf-8",
            )
            client = QdrantClient(path=str(root / "qdrant"))
            try:
                initialize_collection(client, embeddings_file)
                records, _ = client.scroll(
                    collection_name=COLLECTION_NAME,
                    limit=10,
                    with_payload=True,
                )
                self.assertEqual(len(records), 1)
                self.assertEqual(records[0].payload["text"], "Passage de test")
            finally:
                client.close()

    def test_replacing_document_points_removes_stale_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            client = QdrantClient(path=str(Path(directory) / "qdrant"))
            vector = [1.0] + [0.0] * 1023
            old_id = str(uuid4())
            new_id = str(uuid4())
            try:
                replace_document_points(
                    client,
                    "guide.pdf",
                    [
                        PointStruct(
                            id=old_id,
                            vector=vector,
                            payload={"document": "guide.pdf", "text": "Ancien passage"},
                        )
                    ],
                )
                replace_document_points(
                    client,
                    "guide.pdf",
                    [
                        PointStruct(
                            id=new_id,
                            vector=vector,
                            payload={"document": "guide.pdf", "text": "Nouveau passage"},
                        )
                    ],
                )

                records, _ = client.scroll(
                    collection_name=COLLECTION_NAME,
                    limit=10,
                    with_payload=True,
                )
                self.assertEqual([record.id for record in records], [new_id])
                self.assertEqual(records[0].payload["text"], "Nouveau passage")
            finally:
                client.close()

    def test_document_counts_and_deletion_are_scoped_to_one_pdf(self):
        with tempfile.TemporaryDirectory() as directory:
            client = QdrantClient(path=str(Path(directory) / "qdrant"))
            vector = [1.0] + [0.0] * 1023
            try:
                for document in ("first.pdf", "second.pdf"):
                    replace_document_points(
                        client,
                        document,
                        [
                            PointStruct(
                                id=str(uuid4()),
                                vector=vector,
                                payload={"document": document, "text": "Passage"},
                            )
                            for _ in range(2)
                        ],
                    )

                self.assertEqual(
                    count_document_points(client),
                    {"first.pdf": 2, "second.pdf": 2},
                )
                self.assertEqual(delete_document_points(client, "first.pdf"), 2)
                self.assertEqual(
                    count_document_points(client),
                    {"second.pdf": 2},
                )
            finally:
                client.close()

    def test_embedding_snapshot_tracks_document_replacement_and_removal(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "embeddings.json"
            snapshot.write_text(
                json.dumps(
                    [
                        {"document": "guide.pdf", "chunk_id": "old"},
                        {"document": "keep.pdf", "chunk_id": "keep"},
                    ]
                ),
                encoding="utf-8",
            )
            point = PointStruct(
                id=str(uuid4()),
                vector=[1.0] + [0.0] * 1023,
                payload={
                    "document": "guide.pdf",
                    "page": 4,
                    "page_start": 4,
                    "page_end": 5,
                    "section": "Test",
                    "chunk_index": 0,
                    "text": "Nouveau passage",
                },
            )

            self.assertEqual(
                replace_document_embeddings(snapshot, "guide.pdf", [point]),
                1,
            )
            content = json.loads(snapshot.read_text(encoding="utf-8"))
            self.assertEqual(
                [(item["document"], item["chunk_id"]) for item in content],
                [("keep.pdf", "keep"), ("guide.pdf", point.id)],
            )
            self.assertEqual(
                remove_document_embeddings(snapshot, "guide.pdf"),
                1,
            )
            content = json.loads(snapshot.read_text(encoding="utf-8"))
            self.assertEqual([item["document"] for item in content], ["keep.pdf"])

    def test_document_backup_restores_pdf_embeddings_and_qdrant_points(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            documents = root / "documents"
            documents.mkdir()
            pdf = documents / "guide.pdf"
            pdf.write_bytes(b"original pdf")
            embeddings = root / "embeddings.json"
            vector = [1.0] + [0.0] * 1023
            point = PointStruct(
                id=str(uuid4()),
                vector=vector,
                payload={
                    "document": "guide.pdf",
                    "page": 1,
                    "page_start": 1,
                    "page_end": 1,
                    "section": "Guide",
                    "chunk_index": 0,
                    "text": "Original passage",
                },
            )
            embeddings.write_text(
                json.dumps(
                    [{
                        "chunk_id": point.id,
                        "document": "guide.pdf",
                        "page": 1,
                        "page_start": 1,
                        "page_end": 1,
                        "section": "Guide",
                        "chunk_index": 0,
                        "text": "Original passage",
                        "embedding": vector,
                    }]
                ),
                encoding="utf-8",
            )
            backup_root = root / "backups"
            client = QdrantClient(path=str(root / "qdrant"))
            try:
                replace_document_points(client, "guide.pdf", [point])
                backup = create_document_backup(
                    pdf,
                    embeddings,
                    client,
                    backup_root,
                )
                pdf.write_bytes(b"changed pdf")
                delete_document_points(client, "guide.pdf")
                remove_document_embeddings(embeddings, "guide.pdf")

                restored = restore_document_backup(
                    backup["id"],
                    pdf,
                    embeddings,
                    client,
                    backup_root,
                )
                records, _ = client.scroll(
                    collection_name=COLLECTION_NAME,
                    limit=10,
                    with_payload=True,
                    with_vectors=True,
                )
                self.assertEqual(restored["id"], backup["id"])
                self.assertEqual(pdf.read_bytes(), b"original pdf")
                self.assertEqual(len(json.loads(embeddings.read_text("utf-8"))), 1)
                self.assertEqual(len(records), 1)
                self.assertEqual(records[0].payload["text"], "Original passage")
            finally:
                client.close()

    def test_conversation_backup_can_be_restored_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "conversations.sqlite3"
            with patch.object(chat_store, "DATABASE_PATH", database):
                original_id = chat_store.save_conversation(
                    None,
                    [{"role": "user", "content": "Avant"}],
                )
                backup = create_conversation_backup(database, root / "backups")
                chat_store.save_conversation(
                    None,
                    [{"role": "user", "content": "Après"}],
                )
                restored = restore_conversation_backup(
                    backup["id"],
                    database,
                    root / "backups",
                )
                self.assertEqual(restored["id"], backup["id"])
                self.assertEqual(
                    [item["id"] for item in chat_store.list_conversations()],
                    [original_id],
                )


class RetrievalEvaluationTests(unittest.TestCase):
    def test_citation_provenance_matches_document_and_page_to_context(self):
        result = citation_provenance(
            [
                {"document": "guide.pdf", "page": 2},
                {"document": "other.pdf", "page": 2},
            ],
            [{"document": "guide.pdf", "page": 2, "text": "evidence"}],
        )
        self.assertEqual(
            result,
            [
                {
                    "document": "guide.pdf",
                    "page": 2,
                    "available_in_model_context": True,
                },
                {
                    "document": "other.pdf",
                    "page": 2,
                    "available_in_model_context": False,
                },
            ],
        )

    def test_documents_are_included_by_default_and_can_be_excluded_by_name(self):
        chunks = [
            {"document": "ouvrage_1.pdf"},
            {"document": "ouvrage_2.pdf"},
        ]
        candidates = [
            SimpleNamespace(payload={"document": "ouvrage_1.pdf"}),
            SimpleNamespace(payload={"document": "ouvrage_2.pdf"}),
        ]
        self.assertEqual(parse_excluded_documents(None), set())
        self.assertEqual(len(apply_document_exclusions(candidates, set())), 2)
        self.assertEqual(len(apply_document_exclusions(chunks, set())), 2)
        excluded = parse_excluded_documents(" ouvrage_2.pdf, ,ouvrage_3.pdf ")
        self.assertEqual(
            [
                item.payload["document"]
                for item in apply_document_exclusions(candidates, excluded)
            ],
            ["ouvrage_1.pdf"],
        )
        self.assertEqual(
            [item["document"] for item in apply_document_exclusions(chunks, excluded)],
            ["ouvrage_1.pdf"],
        )

    def test_evaluation_matches_expected_document_and_page_ranges(self):
        expected = [
            {"document": "ouvrage_2.pdf", "page_start": 21, "page_end": 23}
        ]
        self.assertTrue(
            source_matches(
                {"document": "ouvrage_2.pdf", "page_start": 22},
                expected,
            )
        )
        self.assertFalse(
            source_matches(
                {"document": "ouvrage_1.pdf", "page": 22},
                expected,
            )
        )
        self.assertEqual(
            reciprocal_rank(
                [
                    {"document": "ouvrage_1.pdf", "page": 1},
                    {"document": "ouvrage_2.pdf", "page": 22},
                ],
                expected,
            ),
            0.5,
        )

    def test_answer_evaluation_checks_expected_facts_and_cited_pages(self):
        result = evaluate_answer(
            "L’ETL extrait les données et les consolide dans un entrepôt.",
            [{"document": "guide.pdf", "page": 2}],
            [
                {"label": "Extraction", "any_terms": ["extrait les donnees"]},
                {"label": "Entrepôt", "any_terms": ["entrepot"]},
            ],
            [{"document": "guide.pdf", "page_start": 1, "page_end": 3}],
        )
        self.assertEqual(result["fact_coverage"], 1.0)
        self.assertEqual(result["source_coverage"], 1.0)
        self.assertTrue(result["passes_lexical_checks"])

        unsupported = evaluate_answer(
            "L’ETL extrait les données.",
            [],
            [{"label": "Entrepôt", "any_terms": ["entrepot"]}],
            [{"document": "guide.pdf", "page_start": 1, "page_end": 3}],
        )
        self.assertEqual(unsupported["fact_coverage"], 0.0)
        self.assertFalse(unsupported["passes_lexical_checks"])

    def test_xai_trace_persists_retrieval_context_citations_and_answer(self):
        with tempfile.TemporaryDirectory() as directory:
            trace_file = Path(directory) / "xai_trace.jsonl"
            trace = {
                "request_id": "request-1",
                "retrieval_path": [{"document": "guide.pdf", "page": 4}],
                "selected_context": [{"text": "Evidence"}],
                "final_sources": [{"document": "guide.pdf", "page": 4}],
                "graph_context": {"available": False},
            }
            with (
                patch("src.xai_trace.XAI_TRACE_FILE", trace_file),
                patch.dict("os.environ", {"XAI_TRACE_ENABLED": "true"}),
            ):
                write_xai_trace(trace, "success", answer="Answer")

            event = json.loads(trace_file.read_text(encoding="utf-8"))
            self.assertEqual(event["request_id"], "request-1")
            self.assertEqual(event["retrieval_path"], trace["retrieval_path"])
            self.assertEqual(event["selected_context"], trace["selected_context"])
            self.assertEqual(event["final_sources"], trace["final_sources"])
            self.assertEqual(event["answer"], "Answer")

    def test_xai_trace_is_disabled_when_setting_is_absent(self):
        with tempfile.TemporaryDirectory() as directory:
            trace_file = Path(directory) / "xai_trace.jsonl"
            with (
                patch("src.xai_trace.XAI_TRACE_FILE", trace_file),
                patch.dict("os.environ", {}, clear=True),
            ):
                write_xai_trace(
                    {"request_id": "request-2"},
                    "success",
                    answer="Private answer",
                )

            self.assertFalse(trace_file.exists())

    def test_audit_log_is_disabled_when_setting_is_absent(self):
        with tempfile.TemporaryDirectory() as directory:
            audit_file = Path(directory) / "audit.jsonl"
            with (
                patch("src.audit_logger.AUDIT_FILE", audit_file),
                patch.dict("os.environ", {}, clear=True),
            ):
                write_audit_log({"question": "Private question"})

            self.assertFalse(audit_file.exists())

    def test_audit_log_can_be_enabled_explicitly(self):
        with tempfile.TemporaryDirectory() as directory:
            audit_file = Path(directory) / "audit.jsonl"
            with (
                patch("src.audit_logger.AUDIT_FILE", audit_file),
                patch("src.audit_logger.LOG_DIR", Path(directory)),
                patch.dict("os.environ", {"AUDIT_LOG_ENABLED": "true"}),
            ):
                write_audit_log({"question": "Authorized test"})

            self.assertEqual(
                json.loads(audit_file.read_text(encoding="utf-8")),
                {"question": "Authorized test"},
            )


if __name__ == "__main__":
    unittest.main()
