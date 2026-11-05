
import os
import json
import time
import html

from queue import Queue, Empty
from threading import Thread

import requests
import streamlit as st
from pathlib import Path
from dotenv import load_dotenv

from src.chat_store import (
    delete_conversation,
    list_conversations,
    load_conversation,
    save_conversation,
)
from src.console import configure_console_encoding


PROJECT_DIR = Path(__file__).resolve().parent.parent
configure_console_encoding()
load_dotenv(PROJECT_DIR / ".env")

# ============================================================
# CONFIGURATION
# ============================================================

os.environ["NO_PROXY"] = "127.0.0.1,localhost"

API_BASE_URL = os.getenv(
    "RSLM_API_URL",
    "http://127.0.0.1:8080",
).rstrip("/")
API_URL = f"{API_BASE_URL}/chat/stream"


st.set_page_config(
    page_title="RSLM",
    page_icon="R",
    layout="centered",
    initial_sidebar_state="collapsed",
)


# ============================================================
# STYLE GLOBAL
# ============================================================

st.markdown(
    """
    <style>
    .block-container {
        max-width: 900px;
        padding-top: 1.6rem;
        padding-bottom: 7rem;
    }

    [data-testid="stChatMessage"] {
        padding-top: 0.55rem;
        padding-bottom: 0.55rem;
    }

    [data-testid="stBottomBlockContainer"] {
        padding-top: 0.55rem;
        border-top: 1px solid rgba(128, 128, 128, 0.18);
    }

    .rslm-disclaimer {
        width: 100%;
        text-align: center;
        font-size: 0.75rem;
        line-height: 1.4;
        color: #888888;
        padding-top: 0.35rem;
    }

    .rslm-welcome {
        padding-top: 3rem;
        padding-bottom: 2rem;
        text-align: center;
    }

    .rslm-welcome-subtitle {
        color: var(--text-color);
        opacity: 0.72;
        font-size: 0.98rem;
        line-height: 1.6;
    }

    @media (prefers-reduced-motion: reduce) {
        * {
            scroll-behavior: auto !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# EN-TÊTE
# ============================================================

# ============================================================
# EN-TÊTE RSLM
# ============================================================

st.title("RSLM")
st.caption("Assistant documentaire local · Java, SQL, Shell, PL/SQL")

st.divider()
# ============================================================
# HISTORIQUE DE CONVERSATION
# ============================================================

if "messages" not in st.session_state:
    st.session_state.messages = []
st.session_state.setdefault("conversation_id", None)
st.session_state.setdefault("feedback_sent", set())


def render_sources(sources, request_id):
    if not sources:
        return

    with st.expander("Sources documentaires"):
        for index, source in enumerate(sources):
            if isinstance(source, dict):
                document = source.get("document", "Document")
                page = source.get("page", "?")
                url = source.get("url")
                if url:
                    st.link_button(
                        f"{document} · page {page}",
                        url,
                        key=f"source-{request_id}-{index}",
                        icon=":material/open_in_new:",
                    )
                else:
                    st.markdown(f"**{document} · page {page}**")
                if source.get("extrait"):
                    st.caption(source["extrait"])
            else:
                st.write(source)


def render_feedback(message):
    request_id = message.get("request_id")
    if not request_id:
        return
    if message.get("feedback") is not None:
        st.session_state.feedback_sent.add(request_id)
    rating = st.feedback(
        "thumbs",
        key=f"feedback-{request_id}",
        default=message.get("feedback"),
        disabled=request_id in st.session_state.feedback_sent,
    )
    if rating is None or request_id in st.session_state.feedback_sent:
        return
    try:
        response = requests.post(
            f"{API_BASE_URL}/feedback",
            json={"request_id": request_id, "rating": rating},
            timeout=10,
        )
        response.raise_for_status()
        message["feedback"] = rating
        st.session_state.feedback_sent.add(request_id)
        if st.session_state.conversation_id is not None:
            save_conversation(
                st.session_state.conversation_id,
                st.session_state.messages,
            )
        st.toast("Merci pour votre retour.")
    except requests.RequestException as error:
        st.error(f"Impossible d’enregistrer votre retour : {error}")


def start_new_conversation():
    st.session_state.conversation_id = None
    st.session_state.messages = []
    st.session_state.history_selector = None


def remove_current_conversation():
    conversation_id = st.session_state.conversation_id
    if conversation_id is not None:
        delete_conversation(conversation_id)
    st.session_state.conversation_id = None
    st.session_state.messages = []
    st.session_state.history_selector = None


with st.sidebar:
    st.subheader("Conversations")
    st.button(
        "Nouvelle conversation",
        key="new-conversation",
        icon=":material/add:",
        width="stretch",
        on_click=start_new_conversation,
    )

    saved_conversations = list_conversations()
    conversation_titles = {
        item["id"]: f"{item['title']} · {item['updated_at'][:10]}"
        for item in saved_conversations
    }
    selected_conversation = st.selectbox(
        "Historique enregistré",
        options=[None] + list(conversation_titles),
        format_func=lambda value: (
            "Conversation en cours"
            if value is None
            else conversation_titles[value]
        ),
        key="history_selector",
    )
    if (
        selected_conversation is not None
        and selected_conversation != st.session_state.conversation_id
    ):
        st.session_state.conversation_id = selected_conversation
        st.session_state.messages = load_conversation(selected_conversation)
        st.rerun()

    if st.session_state.conversation_id is not None:
        st.button(
            "Supprimer cette conversation",
            key="delete-conversation",
            icon=":material/delete:",
            width="stretch",
            on_click=remove_current_conversation,
        )

    if st.session_state.messages:
        st.download_button(
            "Exporter la conversation",
            data=json.dumps(
                st.session_state.messages,
                ensure_ascii=False,
                indent=2,
            ),
            file_name="conversation-RSLM.json",
            mime="application/json",
            key="export-conversation",
            icon=":material/download:",
            width="stretch",
        )

    st.divider()
    st.subheader("Ajouter un document")
    admin_key = st.text_input(
        "Clé administrateur",
        type="password",
        key="admin_key",
        help="La clé doit être configurée dans RSLM_ADMIN_KEY côté API.",
    )
    uploaded_pdf = st.file_uploader(
        "PDF à indexer",
        type=["pdf"],
        max_upload_size=25,
        key="pdf-upload",
    )
    if st.button(
        "Importer et indexer",
        key="upload-pdf",
        disabled=not admin_key or uploaded_pdf is None,
        icon=":material/upload_file:",
        width="stretch",
    ):
        try:
            response = requests.post(
                f"{API_BASE_URL}/admin/documents",
                headers={"X-Admin-Key": admin_key},
                files={
                    "file": (
                        uploaded_pdf.name,
                        uploaded_pdf.getvalue(),
                        "application/pdf",
                    )
                },
                timeout=(10, 600),
            )
            response.raise_for_status()
            result = response.json()
            st.success(
                f"{result['document']} indexé "
                f"({result['chunks_indexed']} passages)."
            )
        except requests.HTTPError as error:
            detail = error.response.text if error.response else str(error)
            st.error(f"Échec de l’import : {detail}")
        except requests.RequestException as error:
            st.error(f"Impossible de joindre l’API : {error}")

    st.divider()
    st.subheader("Corpus documentaire")
    if admin_key:
        try:
            response = requests.get(
                f"{API_BASE_URL}/admin/documents",
                headers={"X-Admin-Key": admin_key},
                timeout=15,
            )
            response.raise_for_status()
            documents = response.json()["documents"]
            if documents:
                status_labels = {
                    "indexed": "Indexé",
                    "not_indexed": "À indexer",
                    "file_missing": "Fichier absent",
                }
                st.dataframe(
                    [
                        {
                            "Document": item["document"],
                            "État": status_labels.get(item["status"], item["status"]),
                            "Passages": item["chunks_indexed"],
                        }
                        for item in documents
                    ],
                    hide_index=True,
                    height=min(260, 38 + 35 * len(documents)),
                )
                selected_document = st.selectbox(
                    "Document à gérer",
                    options=[item["document"] for item in documents],
                    key="admin-document-selection",
                )
                if selected_document:
                    selected_entry = next(
                        item
                        for item in documents
                        if item["document"] == selected_document
                    )
                    if selected_entry["status"] == "file_missing":
                        st.caption(
                            "Le PDF source est absent ; les passages orphelins "
                            "peuvent être supprimés du corpus."
                        )
                    if st.button(
                        "Réindexer le document",
                        key="reindex-document",
                        disabled=selected_entry["status"] == "file_missing",
                        icon=":material/refresh:",
                        width="stretch",
                    ):
                        try:
                            result = requests.post(
                                f"{API_BASE_URL}/admin/documents/"
                                f"{requests.utils.quote(selected_document, safe='')}/reindex",
                                headers={"X-Admin-Key": admin_key},
                                timeout=(10, 600),
                            )
                            result.raise_for_status()
                            st.success(
                                f"{selected_document} réindexé "
                                f"({result.json()['chunks_indexed']} passages)."
                            )
                            st.rerun()
                        except requests.HTTPError as error:
                            detail = error.response.text if error.response else str(error)
                            st.error(f"Échec de la réindexation : {detail}")
                        except requests.RequestException as error:
                            st.error(f"Impossible de joindre l’API : {error}")

                    confirm_delete = st.checkbox(
                        f"Confirmer la suppression de {selected_document}",
                        key=f"confirm-document-delete-{selected_document}",
                    )
                    if st.button(
                        "Supprimer du corpus",
                        key="delete-document",
                        disabled=not confirm_delete,
                        icon=":material/delete:",
                        width="stretch",
                    ):
                        try:
                            result = requests.delete(
                                f"{API_BASE_URL}/admin/documents/"
                                f"{requests.utils.quote(selected_document, safe='')}",
                                headers={"X-Admin-Key": admin_key},
                                timeout=30,
                            )
                            result.raise_for_status()
                            st.success(
                                f"{selected_document} supprimé "
                                f"({result.json()['chunks_deleted']} passages retirés)."
                            )
                            st.rerun()
                        except requests.HTTPError as error:
                            detail = error.response.text if error.response else str(error)
                            st.error(f"Échec de la suppression : {detail}")
                        except requests.RequestException as error:
                            st.error(f"Impossible de joindre l’API : {error}")
            else:
                st.caption("Aucun PDF dans le corpus.")
        except requests.HTTPError as error:
            detail = error.response.text if error.response else str(error)
            st.error(f"Impossible de charger le corpus : {detail}")
        except requests.RequestException as error:
            st.error(f"Impossible de joindre l’API : {error}")

        st.divider()
        st.subheader("Sauvegardes et restauration")

        if st.button(
            "Sauvegarder les conversations",
            key="backup-conversations",
            icon=":material/backup:",
            width="stretch",
        ):
            try:
                result = requests.post(
                    f"{API_BASE_URL}/admin/backups/conversations",
                    headers={"X-Admin-Key": admin_key},
                    timeout=30,
                )
                result.raise_for_status()
                st.success(
                    f"Sauvegarde créée le {result.json()['created_at']}."
                )
                st.rerun()
            except requests.HTTPError as error:
                detail = error.response.text if error.response else str(error)
                st.error(f"Échec de la sauvegarde : {detail}")
            except requests.RequestException as error:
                st.error(f"Impossible de joindre l’API : {error}")

        try:
            response = requests.get(
                f"{API_BASE_URL}/admin/backups/documents",
                headers={"X-Admin-Key": admin_key},
                timeout=15,
            )
            response.raise_for_status()
            document_backups = response.json()["backups"]
            if document_backups:
                backups_by_id = {
                    item["id"]: item for item in document_backups
                }
                selected_backup_id = st.selectbox(
                    "Sauvegarde d’un document",
                    options=[None] + list(backups_by_id),
                    format_func=lambda value: (
                        "Choisir une sauvegarde"
                        if value is None
                        else (
                            f"{backups_by_id[value]['document']} · "
                            f"{backups_by_id[value]['created_at'][:19]}"
                        )
                    ),
                    key="document-backup-selection",
                )
                if selected_backup_id:
                    backup = backups_by_id[selected_backup_id]
                    st.caption(
                        f"PDF : {'oui' if backup['pdf_present'] else 'non'} · "
                        f"Passages : {backup['qdrant_points']}"
                    )
                    confirm_restore = st.checkbox(
                        f"Confirmer la restauration de {backup['document']}",
                        key=f"confirm-document-restore-{selected_backup_id}",
                    )
                    if st.button(
                        "Restaurer cette sauvegarde",
                        key="restore-document-backup",
                        disabled=not confirm_restore,
                        icon=":material/restore:",
                        width="stretch",
                    ):
                        try:
                            result = requests.post(
                                f"{API_BASE_URL}/admin/documents/"
                                f"{requests.utils.quote(backup['document'], safe='')}/restore/"
                                f"{selected_backup_id}",
                                headers={"X-Admin-Key": admin_key},
                                timeout=(10, 60),
                            )
                            result.raise_for_status()
                            st.success(
                                f"{backup['document']} restauré ; l’état qui "
                                "précédait la restauration est également sauvegardé."
                            )
                            st.rerun()
                        except requests.HTTPError as error:
                            detail = error.response.text if error.response else str(error)
                            st.error(f"Échec de la restauration : {detail}")
                        except requests.RequestException as error:
                            st.error(f"Impossible de joindre l’API : {error}")
            else:
                st.caption("Aucune sauvegarde de document pour le moment.")
        except requests.HTTPError as error:
            detail = error.response.text if error.response else str(error)
            st.error(f"Impossible de charger les sauvegardes : {detail}")
        except requests.RequestException as error:
            st.error(f"Impossible de joindre l’API : {error}")

        try:
            response = requests.get(
                f"{API_BASE_URL}/admin/backups/conversations",
                headers={"X-Admin-Key": admin_key},
                timeout=15,
            )
            response.raise_for_status()
            conversation_backups = response.json()["backups"]
            if conversation_backups:
                conversation_backups_by_id = {
                    item["id"]: item for item in conversation_backups
                }
                selected_conversation_backup = st.selectbox(
                    "Sauvegarde de conversations",
                    options=[None] + list(conversation_backups_by_id),
                    format_func=lambda value: (
                        "Choisir une sauvegarde"
                        if value is None
                        else conversation_backups_by_id[value]["created_at"][:19]
                    ),
                    key="conversation-backup-selection",
                )
                if selected_conversation_backup:
                    confirm_restore_conversations = st.checkbox(
                        "Confirmer le remplacement de l’historique par cette sauvegarde",
                        key=(
                            "confirm-conversation-restore-"
                            f"{selected_conversation_backup}"
                        ),
                    )
                    if st.button(
                        "Restaurer les conversations",
                        key="restore-conversation-backup",
                        disabled=not confirm_restore_conversations,
                        icon=":material/restore:",
                        width="stretch",
                    ):
                        try:
                            result = requests.post(
                                f"{API_BASE_URL}/admin/backups/conversations/"
                                f"{selected_conversation_backup}/restore",
                                headers={"X-Admin-Key": admin_key},
                                timeout=30,
                            )
                            result.raise_for_status()
                            st.success(
                                "Historique restauré ; l’historique remplacé "
                                "est lui aussi sauvegardé."
                            )
                            st.rerun()
                        except requests.HTTPError as error:
                            detail = error.response.text if error.response else str(error)
                            st.error(f"Échec de la restauration : {detail}")
                        except requests.RequestException as error:
                            st.error(f"Impossible de joindre l’API : {error}")
            else:
                st.caption("Aucune sauvegarde de conversations pour le moment.")
        except requests.HTTPError as error:
            detail = error.response.text if error.response else str(error)
            st.error(f"Impossible de charger les sauvegardes : {detail}")
        except requests.RequestException as error:
            st.error(f"Impossible de joindre l’API : {error}")
    else:
        st.caption("Saisissez la clé administrateur pour consulter le corpus.")


# ============================================================
# CHAMP DE SAISIE FIXE ET MENTION LÉGALE
# ============================================================

with st.bottom:

    question = st.chat_input(
        "Posez votre question…",
        key="rslm_chat_input",
        submit_mode="disable",
    )

    st.markdown(
        """
        <div class="rslm-disclaimer">
            RSLM peut faire des erreurs.
            Vérifiez les informations importantes.
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# ÉCRAN D'ACCUEIL
# ============================================================

if not st.session_state.messages and not question:
    suggestion = st.pills(
        "Essayez une question",
        [
            "Comment configurer tSortRow ?",
            "À quoi sert tMap dans un outil ETL ?",
            "Comment utiliser une regex Java ?",
            "Comment générer une fonction PL/SQL ?",
        ],
        key="question-suggestions",
        label_visibility="collapsed",
    )
    if suggestion:
        question = suggestion


# ============================================================
# FONCTION : AFFICHER LE STATUT D'ATTENTE
# ============================================================

def afficher_statut_attente(
    placeholder,
    message: str = "",
    afficher_roue: bool = False,
):

    html_modele = """
    <style>
    @keyframes assistant-spin {
        to {
            transform: rotate(360deg);
        }
    }

    @keyframes assistant-text-pulse {
        0%, 100% {
            opacity: 1;
        }

        50% {
            opacity: 0.65;
        }
    }

    @keyframes assistant-dots {
        0%, 20% {
            opacity: 0.2;
        }

        50% {
            opacity: 1;
        }

        100% {
            opacity: 0.2;
        }
    }

    .assistant-thinking {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 12px 2px;
        color: var(--text-color);
        font-size: 0.95rem;
    }

    .assistant-spinner {
        width: 17px;
        height: 17px;
        flex-shrink: 0;
        border: 2px solid rgba(128, 128, 128, 0.25);
        border-top-color: #4F8DF7;
        border-radius: 50%;
        animation: assistant-spin 0.8s linear infinite;
    }

    .assistant-label {
        font-weight: 500;
        animation: assistant-text-pulse 2.2s ease-in-out infinite;
    }

    .assistant-dots {
        display: inline-flex;
        gap: 3px;
        margin-left: -8px;
    }

    .assistant-dots span {
        animation: assistant-dots 1.2s infinite;
        opacity: 0.2;
    }

    .assistant-dots span:nth-child(2) {
        animation-delay: 0.2s;
    }

    .assistant-dots span:nth-child(3) {
        animation-delay: 0.4s;
    }

    @media (prefers-reduced-motion: reduce) {
        .assistant-spinner,
        .assistant-label,
        .assistant-dots span {
            animation: none;
        }

        .assistant-dots span {
            opacity: 1;
        }
    }
    </style>

    <div class="assistant-thinking" role="status" aria-live="polite">
        __SPINNER__
        __MESSAGE__
        __DOTS__
    </div>
    """

    spinner_html = (
        '<span class="assistant-spinner"></span>'
        if afficher_roue
        else ""
    )

    message_html = (
        '<span class="assistant-label">'
        + html.escape(message)
        + '</span>'
        if message
        else ""
    )

    dots_html = (
        '<span class="assistant-dots" aria-hidden="true">'
        '<span>.</span><span>.</span><span>.</span>'
        '</span>'
        if message
        else ""
    )

    contenu_html = (
        html_modele
        .replace("__SPINNER__", spinner_html)
        .replace("__MESSAGE__", message_html)
        .replace("__DOTS__", dots_html)
    )

    placeholder.html(contenu_html)


# ============================================================
# FONCTION : LECTURE DU FLUX API EN ARRIÈRE-PLAN
# ============================================================

def lire_flux_api(payload, events):

    try:

        with requests.post(
            API_URL,
            json=payload,
            stream=True,
            timeout=(10, 120),
        ) as response:

            response.raise_for_status()

            for line in response.iter_lines(
                decode_unicode=True,
                chunk_size=1,
            ):

                if not line:
                    continue

                if not line.startswith("data: "):
                    continue

                try:

                    data = json.loads(line[6:])

                except json.JSONDecodeError:

                    continue

                events.put(("data", data))

        events.put(("done", None))

    except Exception as e:

        events.put(("exception", e))


# ============================================================
# AFFICHAGE DE L'HISTORIQUE EXISTANT
# ============================================================

for msg in st.session_state.messages:

    with st.chat_message(msg["role"]):

        st.markdown(msg["content"])
        if msg["role"] == "assistant":
            render_sources(msg.get("sources", []), msg.get("request_id"))
            if msg.get("score_confiance") is not None:
                st.caption(
                    f"Score de recherche : {msg['score_confiance']:.2f} "
                    "(indicateur de pertinence, pas une probabilité)"
                )
            render_feedback(msg)

# ============================================================
# TRAITEMENT D'UNE NOUVELLE QUESTION
# ============================================================

if question:

    # --------------------------------------------------------
    # AFFICHER LA QUESTION UTILISATEUR
    # --------------------------------------------------------

    with st.chat_message("user"):

        st.markdown(question)

    # --------------------------------------------------------
    # PRÉPARER L'HISTORIQUE POUR L'API
    # --------------------------------------------------------

    historique_api = [
        {
            "role": message["role"],
            "content": message["content"],
        }
        for message in st.session_state.messages[-4:]
    ]

    payload = {
        "question": question,
        "historique": historique_api,
    }

    # --------------------------------------------------------
    # RÉPONSE ASSISTANT
    # --------------------------------------------------------

    with st.chat_message("assistant"):

        # Ordre volontaire : statut au-dessus de la réponse.
        status_placeholder = st.empty()
        message_placeholder = st.empty()

        full_response = ""
        sources = []
        score = 0.0
        request_id = None

        first_token_received = False
        final_received = False

        request_start = time.perf_counter()

        events = Queue()

        last_status_message = None
        last_status_roue = None

        worker = Thread(
            target=lire_flux_api,
            args=(payload, events),
            daemon=True,
        )

        try:

            worker.start()

            # ------------------------------------------------
            # LECTURE DU FLUX
            # ------------------------------------------------

            while True:

                # --------------------------------------------
                # STATUT D'ATTENTE
                # --------------------------------------------

                if not first_token_received:

                    elapsed_wait = (
                        time.perf_counter() - request_start
                    )

                    if elapsed_wait < 4:

                        current_status_message = ""
                        current_status_roue = True

                    elif elapsed_wait < 9:

                        current_status_message = (
                            "Je prépare une réponse adaptée "
                            "à votre question…"
                        )

                        current_status_roue = False

                    elif elapsed_wait <= 13:

                        current_status_message = (
                            "Je rassemble les éléments utiles…"
                        )

                        current_status_roue = False

                    else:

                        current_status_message = (
                            "Je génère la réponse et les sources…"
                        )

                        current_status_roue = False

                    if (
                        current_status_message
                        != last_status_message
                        or current_status_roue
                        != last_status_roue
                    ):

                        afficher_statut_attente(
                            status_placeholder,
                            message=current_status_message,
                            afficher_roue=current_status_roue,
                        )

                        last_status_message = (
                            current_status_message
                        )

                        last_status_roue = (
                            current_status_roue
                        )

                # --------------------------------------------
                # ATTENDRE LE PROCHAIN ÉVÉNEMENT
                # --------------------------------------------

                try:

                    event_type, event = events.get(
                        timeout=0.2
                    )

                except Empty:

                    continue

                if event_type == "done":

                    break

                if event_type == "exception":

                    raise event

                data = event

                # --------------------------------------------
                # TOKEN : DÉBUT DE LA RÉPONSE
                # --------------------------------------------

                if data.get("type") == "token":

                    if not first_token_received:

                        first_token_received = True

                        status_placeholder.empty()

                    full_response += data.get(
                        "content",
                        "",
                    )

                    message_placeholder.markdown(
                        full_response + "▌"
                    )

                # --------------------------------------------
                # RÉPONSE FINALE
                # --------------------------------------------

                elif data.get("type") == "final":

                    status_placeholder.empty()

                    full_response = data.get(
                        "reponse",
                        full_response,
                    )

                    sources = data.get(
                        "sources",
                        [],
                    )

                    score = data.get(
                        "score_confiance",
                        0.0,
                    )
                    request_id = data.get("request_id")

                    final_received = True

                    message_placeholder.markdown(
                        full_response
                    )

                # --------------------------------------------
                # ERREUR SIGNALÉE PAR FASTAPI
                # --------------------------------------------

                elif data.get("type") == "error":

                    status_placeholder.empty()

                    raise RuntimeError(
                        data.get(
                            "content",
                            "Une erreur est survenue.",
                        )
                    )

            # ------------------------------------------------
            # VÉRIFIER LA FIN DU STREAM
            # ------------------------------------------------

            if not final_received:

                raise RuntimeError(
                    "Le flux s'est terminé sans réponse finale."
                )

            status_placeholder.empty()

            # ------------------------------------------------
            # LOG CONSOLE : DURÉE TOTALE
            # ------------------------------------------------

            total_time = (
                time.perf_counter() - request_start
            )

            print(
                f"🏁 Streamlit : réponse terminée "
                f"en {total_time:.2f}s"
            )

            # ------------------------------------------------
            # AFFICHAGE DES SOURCES
            # ------------------------------------------------

            render_sources(sources, request_id)
            st.caption(
                f"Score de recherche : {score:.2f} "
                "(indicateur de pertinence, pas une probabilité)"
            )

            st.download_button(
                "Télécharger la réponse",
                data=full_response,
                file_name="reponse-RSLM.md",
                mime="text/markdown",
                key=f"download-{request_id or time.time_ns()}",
                icon=":material/download:",
            )

            # ------------------------------------------------
            # MÉMORISER LA CONVERSATION
            # ------------------------------------------------

            st.session_state.messages.append(
                {
                    "role": "user",
                    "content": question,
                }
            )

            assistant_message = {
                "role": "assistant",
                "content": full_response,
                "sources": sources,
                "score_confiance": score,
                "request_id": request_id,
            }
            st.session_state.messages.append(assistant_message)
            st.session_state.conversation_id = save_conversation(
                st.session_state.conversation_id,
                st.session_state.messages,
            )
            render_feedback(assistant_message)

        # ----------------------------------------------------
        # ERREUR DE CONNEXION
        # ----------------------------------------------------

        except requests.exceptions.ConnectionError:

            status_placeholder.empty()

            st.error(
                "Impossible de contacter l'API. "
                "Vérifiez que FastAPI fonctionne sur le port 8080."
            )

        # ----------------------------------------------------
        # TIMEOUT
        # ----------------------------------------------------

        except requests.exceptions.Timeout:

            status_placeholder.empty()

            st.error(
                "L'API a mis trop de temps à répondre. "
                "Veuillez réessayer."
            )

        # ----------------------------------------------------
        # AUTRE ERREUR
        # ----------------------------------------------------

        except Exception as e:

            status_placeholder.empty()

            st.error(
                f"Une erreur est survenue : {str(e)}"
            )
