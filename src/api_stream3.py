import os
import json
import time
import re
import asyncio
import hmac
import threading
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
from urllib.parse import quote

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from ollama import AsyncClient
from sentence_transformers import CrossEncoder, SentenceTransformer
from langdetect import detect, LangDetectException


from .audit_logger import (
    generate_request_id,
    create_audit_event,
    write_audit_log,
)
from .api_models import ChatRequest, FeedbackRequest, Message
from .backup_store import (
    create_conversation_backup,
    create_document_backup,
    list_conversation_backups,
    list_document_backups,
    restore_conversation_backup,
    restore_document_backup,
)
from .document_indexer import index_pdf
from .console import configure_console_encoding
from .qdrant_connection import (
    COLLECTION_NAME,
    count_document_points,
    create_qdrant_client,
    delete_document_points,
    initialize_collection,
    remove_document_embeddings,
)
from .retrieval import apply_document_exclusions, parse_excluded_documents
from .xai_trace import citation_provenance, write_xai_trace


# ============================================================
# CONFIGURATION
# ============================================================

configure_console_encoding()
os.environ["TOKENIZERS_PARALLELISM"] = "false"

PROJECT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_DIR / ".env")

DOCUMENTS_DIR = PROJECT_DIR / "documents"
EMBEDDINGS_FILE = PROJECT_DIR / "data" / "embeddings.json"
AUDIT_DIR = PROJECT_DIR / "logs"
BACKUP_DIR = PROJECT_DIR / "data" / "backups"
CONVERSATION_DATABASE_PATH = PROJECT_DIR / "data" / "conversations.sqlite3"

EMBEDDING_MODEL = "BAAI/bge-m3"
RERANKER_MODEL = os.getenv(
    "RERANKER_MODEL",
    "BAAI/bge-reranker-v2-m3",
)
OLLAMA_MODEL = "qwen2.5:1.5b"
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
UPLOAD_ADMIN_KEY = os.getenv("RSLM_ADMIN_KEY", "")
DEBUG_CONTENT_LOGS = os.getenv(
    "RSLM_DEBUG_CONTENT_LOGS",
    "false",
).strip().lower() in {"1", "true", "yes", "on"}
ALLOWED_CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "RSLM_ALLOWED_ORIGINS",
        "http://localhost:5173",
    ).split(",")
    if origin.strip()
]
REQUEST_SEMAPHORE = asyncio.Semaphore(
    max(1, int(os.getenv("MAX_CONCURRENT_CHAT_REQUESTS", "2")))
)

# Nombre de résultats récupérés par Qdrant
RETRIEVAL_LIMIT = max(1, int(os.getenv("RETRIEVAL_LIMIT", "10")))
EXCLUDED_DOCUMENTS = parse_excluded_documents(
    os.getenv("RAG_EXCLUDED_DOCUMENTS")
)

# Nombre de résultats réellement transmis au LLM
FINAL_LIMIT = 3

# ------------------------------------------------------------
# Paramètres Ollama
# ------------------------------------------------------------

OLLAMA_NUM_CTX = 4096
OLLAMA_NUM_THREAD = 4
OLLAMA_TEMPERATURE = 0.1

# ------------------------------------------------------------
# Limitation du contexte envoyé à Qwen
# ------------------------------------------------------------

# Évite d'envoyer des chunks énormes au petit modèle.
MAX_CHARS_PER_CHUNK = 3000
MAX_CONTEXT_CHARS = 7500

# ------------------------------------------------------------
# Guardrail
# ------------------------------------------------------------

# Attention :
# Ce score est un score de similarité Qdrant.
# Ce n'est PAS une probabilité de vérité.
#
# Nous complétons donc ce contrôle avec un contrôle lexical.
MIN_QDRANT_SCORE = 0.50

# Nombre minimal de caractères pour considérer un mot
# comme un terme significatif.
MIN_TERM_LENGTH = 3


# ============================================================
# PROMPT SYSTEME
# ============================================================

SYSTEM_PROMPT = """
Tu es l'assistant documentaire RSLM.

Ton rôle est uniquement de répondre aux questions
à partir des extraits de documentation fournis.

RÈGLES ABSOLUES :

- N'utilise aucune connaissance issue de ton entraînement.
- N'invente aucune information.
- Ne complète jamais une information absente des extraits.
- Ne déduis jamais l'identité, la profession, la nationalité
  ou la biographie d'une personne.
- Ne fais aucune supposition.
- Ne parle jamais de Google Cloud, d'autres produits,
  de personnes ou de sujets absents des extraits.
- Si les extraits ne permettent pas de répondre précisément,
  réponds exactement :
  "Je ne trouve pas d'information permettant de répondre
  à cette question dans la documentation fournie."
- Réponds uniquement à la question posée.
- Ne décris pas tes capacités sauf si l'utilisateur te demande
  explicitement qui tu es.

Les extraits de documentation sont la seule source autorisée.
"""


REFUS_MESSAGE = (
    "Désolé, je n'ai pas accés à cette information. Je serais ravi de pouvoir vous aider si vous avez d'autes questions."
)


# ============================================================
# OBJETS GLOBAUX
# ============================================================

models = {}
ollama_client: Optional[AsyncClient] = None
upload_lock = asyncio.Lock()
feedback_lock = threading.Lock()


# ============================================================
# LIFESPAN
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):

    global ollama_client

    print()
    print("=" * 60)
    print("🚀 CHARGEMENT DU SYSTÈME IA")
    print("=" * 60)

    total_start = time.perf_counter()

    # --------------------------------------------------------
    # BGE-M3
    # --------------------------------------------------------

    print("📥 Chargement de BGE-M3...")

    start = time.perf_counter()

    models["embedding"] = SentenceTransformer(
        EMBEDDING_MODEL
    )

    print(
        f"   ✅ BGE-M3 chargé en "
        f"{time.perf_counter() - start:.2f}s"
    )

    print(f"📥 Chargement du reranker {RERANKER_MODEL}...")
    start = time.perf_counter()
    models["reranker"] = CrossEncoder(RERANKER_MODEL)
    print(
        f"   ✅ Reranker chargé en "
        f"{time.perf_counter() - start:.2f}s"
    )

# Préparation du classificateur d'intentions
    print("📥 Préparation des intentions conversationnelles...")

    models["social_example_labels"] = [
        label for label, _ in SOCIAL_EXAMPLES
    ]

    models["social_embeddings"] = models["embedding"].encode(
        [phrase for _, phrase in SOCIAL_EXAMPLES],
        normalize_embeddings=True,
        show_progress_bar=False,
    )

    print("✅ Classificateur d'intentions prêt.")

    # --------------------------------------------------------
    # Qdrant
    # --------------------------------------------------------

    print("📥 Connexion à Qdrant...")

    start = time.perf_counter()

    for attempt in range(10):
        models["qdrant"] = create_qdrant_client()
        try:
            await asyncio.to_thread(
                models["qdrant"].get_collections
            )
            break
        except Exception as error:
            models["qdrant"].close()
            if attempt == 9:
                raise RuntimeError(
                    "Connexion à Qdrant impossible après 10 tentatives."
                ) from error
            await asyncio.sleep(2)

    try:
        await asyncio.to_thread(
            initialize_collection,
            models["qdrant"],
            EMBEDDINGS_FILE,
        )
    except Exception:
        models["qdrant"].close()
        raise

    print(
        f"   ✅ Qdrant connecté en "
        f"{time.perf_counter() - start:.2f}s"
    )

    # --------------------------------------------------------
    # Ollama
    # --------------------------------------------------------

    ollama_client = AsyncClient(
    host=os.getenv(
        "OLLAMA_HOST",
        "http://127.0.0.1:11434"
    )
)

    print("✅ Client Ollama prêt.")

    print()
    print(
        f"✅ SYSTÈME PRÊT EN "
        f"{time.perf_counter() - total_start:.2f}s"
    )
    print("=" * 60)
    print()

    yield

    # --------------------------------------------------------
    # FERMETURE
    # --------------------------------------------------------

    print("🛑 Fermeture de Qdrant...")

    models["qdrant"].close()

    ollama_client = None


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title="RSLM API",
    version="2.0",
    lifespan=lifespan,
)

DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount(
    "/documents",
    StaticFiles(directory=str(DOCUMENTS_DIR)),
    name="documents",
)
    # --------------------------------------------------------
    # Connexion entre FASTAPI et mon eportfolio
    # --------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

# ============================================================
# MODELES PYDANTIC
# ============================================================

# ============================================================
# NORMALISATION DU TEXTE
# ============================================================

def normaliser_texte(texte: str) -> str:
    """
 Normalise un texte pour les contrôles lexicaux.
    """
    texte = texte.lower()

    # Suppression des accents
    replacements = str.maketrans(
        {
            "à": "a",
            "â": "a",
            "ä": "a",
            "é": "e",
            "è": "e",
            "ê": "e",
            "ë": "e",
            "î": "i",
            "ï": "i",
            "ô": "o",
            "ö": "o",
            "ù": "u",
            "û": "u",
            "ü": "u",
            "ç": "c",
        }
    )

    texte = texte.translate(replacements)

    return texte



# ============================================================
# ROUTAGE DES INTENTIONS CONVERSATIONNELLES
# ============================================================

SOCIAL_INTENT_THRESHOLD = 0.72
SOCIAL_TECH_MARGIN = 0.04

SOCIAL_RESPONSES = {
    "salutation_fr": (
        "Bonjour ! Comment puis-je vous aider avec vos documents ?"
    ),
    "salutation_en": (
        "Hello! How can I help you with your documents?"
    ),
    "bien_etre_fr": (
        "Ça va bien, merci ! Et vous ? 😊"
    ),
    "bien_etre_en": (
        "Thanks for asking! I'm ready to help with your documents. "

    ),
    "identite_fr": (
        "Je suis un assistant documentaire local. "
        "Je réponds aux questions à partir de la documentation disponible."
    ),
    "identite_en": (
        "I'm a local document assistant. "
        "I answer questions using the available documentation."
    ),
    "capacites_fr": (
        "Je peux vous aider à comprendre les sujets décrits dans "
        "vos documents."
    ),
    "capacites_en": (
        "I can help explain topics covered by your documents. "
    ),
    "merci_fr": (
        "Avec plaisir ! Je suis la pour vous aider."
    ),
    "merci_en": (
        "You're welcome! What would you like to know next?"
    ),
    "au_revoir_fr": (
        "Au revoir !"
    ),
    "au_revoir_en": (
        "Goodbye! "
    ),
}


# Exemples sémantiques : ils servent à reconnaître des formulations
# différentes, pas à constituer une liste exhaustive de phrases.
SOCIAL_EXAMPLES = [
    ("salutation_fr", "Bonjour"),
    ("salutation_fr", "Salut"),
    ("salutation_fr", "Bonsoir"),
    ("salutation_fr", "Coucou"),
    ("salutation_en", "Hello"),
    ("salutation_en", "Hi"),
    ("salutation_en", "Hey"),
    ("salutation_en", "Good morning"),

    ("bien_etre_fr", "Comment vas-tu aujourd'hui ?"),
    ("bien_etre_fr", "Est-ce que tu vas bien ?"),
    ("bien_etre_fr", "Comment te sens-tu ?"),
    ("bien_etre_fr", "Quoi de neuf ?"),
    ("bien_etre_en", "How are you?"),
    ("bien_etre_en", "How are you doing today?"),
    ("bien_etre_en", "How is everything going?"),
    ("bien_etre_en", "How do you feel today?"),

    ("identite_fr", "Qui es-tu ?"),
    ("identite_fr", "Tu es qui ?"),
    ("identite_fr", "T'es qui?"),
    ("identite_fr", "Présente-toi."),
    ("identite_fr", "Quel est ton rôle ?"),
    ("identite_en", "Who are you?"),
    ("identite_en", "Tell me about yourself."),
    ("identite_en", "What kind of assistant are you?"),
    ("identite_en", "What is your role?"),

    ("capacites_fr", "Que peux-tu faire ?"),
    ("capacites_fr", "Comment peux-tu m'aider ?"),
    ("capacites_fr", "Quelles sont tes capacités ?"),
    ("capacites_en", "What can you do?"),
    ("capacites_en", "How can you help me?"),
    ("capacites_en", "What are your capabilities?"),

    ("merci_fr", "Merci beaucoup"),
    ("merci_en", "Thank you very much"),
    ("au_revoir_fr", "Au revoir"),
    ("au_revoir_en", "See you later"),

    # Exemples de protection : ces questions ne doivent pas être
    # confondues avec une conversation générale.
    ("question_technique", "À quoi sert le composant tMap dans un outil ETL ?"),
    ("question_technique", "Comment configurer un composant logiciel ?"),
    ("question_technique", "Explique une erreur dans un job ETL."),
    ("question_technique", "Bonjour, comment fonctionne le composant tMap ?"),
    ("question_technique", "What does the tMap component do in an ETL tool?"),
    ("question_technique", "How do I configure a software component?"),
    ("question_technique", "Hello, how do I configure a software component?"),

    # Questions sur une autre personne ou un autre sujet :
    # elles doivent rester soumises aux garde-fous habituels.
    ("question_non_sociale", "Qui est Hani Zitout ?"),
    ("question_non_sociale", "Who is Hani Zitout?"),
    ("question_non_sociale", "Qui est le président des États-Unis ?"),
    ("question_non_sociale", "What is the capital of France?"),
]


# Les expressions les plus courantes sont traitées sans calcul d'embedding.
SOCIAL_FAST_PATTERNS = [
    ("salutation_fr", r"(?:bonjour|bonsoir|salut|coucou)"),
    ("salutation_en", r"(?:hello+|hi+|hey+|yo+|good morning|good afternoon|good evening)"),

    ("bien_etre_fr", r"(?:ca va|comment ca va|comment vas tu|comment tu vas|tu vas bien|comment allez vous)"),
    ("bien_etre_en", r"(?:how are you|how are you doing|how s it going|how is it going|how do you feel)"),

    ("identite_fr", r"(?:qui es tu|tu es qui|qui etes vous|comment tu t appelles|presente toi)"),
    ("identite_en", r"(?:who are you|what are you|what s your name|what is your name|introduce yourself)"),

    ("capacites_fr", r"(?:que peux tu faire|que sais tu faire|comment peux tu m aider|peux tu m aider)"),
    ("capacites_en", r"(?:what can you do|how can you help me|can you help me|what are your capabilities)"),

    ("merci_fr", r"(?:merci|merci beaucoup|je te remercie|je vous remercie)"),
    ("merci_en", r"(?:thanks|thank you|thanks a lot|thank you very much)"),

    ("au_revoir_fr", r"(?:au revoir|a bientot|bonne journee|bonne soiree|a plus)"),
    ("au_revoir_en", r"(?:bye|goodbye|see you|see you later|take care)"),
]


def normaliser_sociale(texte: str) -> str:
    texte = normaliser_texte(texte)
    texte = re.sub(r"[^\w\s]", " ", texte)
    return re.sub(r"\s+", " ", texte).strip()


def detecter_intention_sociale(question: str):
    """
    Retourne :
    - la réponse directe si l'intention sociale est reconnue ;
    - le vecteur calculé, réutilisable pour la recherche RAG ;
    - le temps d'encodage ;
    - l'intention reconnue.
    """

    texte = normaliser_sociale(question)

    # 1. Détection rapide des formulations courantes
    for intention, pattern in SOCIAL_FAST_PATTERNS:
        if re.fullmatch(pattern, texte):
            return (
                SOCIAL_RESPONSES[intention],
                None,
                0.0,
                intention,
            )

    # 2. Encodage sémantique avec BGE-M3
    start = time.perf_counter()

    vecteur_question = models["embedding"].encode(
        question,
        normalize_embeddings=True,
    )

    embedding_time = time.perf_counter() - start

    # 3. Comparaison avec les intentions pré-encodées
    vecteurs = models["social_embeddings"]
    labels = models["social_example_labels"]

    scores = vecteurs @ vecteur_question
    scores_par_intention = {}

    for label, score in zip(labels, scores):
        score = float(score)

        scores_par_intention[label] = max(
            score,
            scores_par_intention.get(label, -1.0),
        )

    # Meilleure intention conversationnelle
    intentions_sociales = {
        label: score
        for label, score in scores_par_intention.items()
        if label in SOCIAL_RESPONSES
    }

    meilleure_intention = max(
        intentions_sociales,
        key=intentions_sociales.get,
    )

    meilleur_score_social = intentions_sociales[
        meilleure_intention
    ]

    # Une question technique ou hors sujet doit primer si elle
    # ressemble davantage à ces exemples qu'à une conversation.
    score_non_social = max(
        (
            score
            for label, score in scores_par_intention.items()
            if label not in SOCIAL_RESPONSES
        ),
        default=-1.0,
    )

    print(
        f"🧭 Routage : {meilleure_intention}="
        f"{meilleur_score_social:.3f} | "
        f"non_social={score_non_social:.3f}"
    )

    # Protection : "Qui est Hani Zitout ?" ne signifie pas
    # "Qui es-tu ?". Pour une intention d'identité, on cherche
    # un indice clair faisant référence à l'assistant.
    mots = set(texte.split())

    references_a_soi = {
        "tu", "toi", "vous", "ton", "ta", "tes",
        "you", "your", "yourself",
        "assistant", "chatbot", "bot", "ia",
    }

    if (
        meilleure_intention.startswith("identite_")
        and not mots.intersection(references_a_soi)
    ):
        return None, vecteur_question, embedding_time, None

    # Seules les intentions suffisamment proches et nettement
    # plus sociales que les exemples non sociaux sont retenues.
    if (
        meilleur_score_social >= SOCIAL_INTENT_THRESHOLD
        and meilleur_score_social >= score_non_social + SOCIAL_TECH_MARGIN
    ):
        # Détecter la langue du message de l'utilisateur
        try:
            langue = detect(question)
        except LangDetectException:
            langue = "fr" if meilleure_intention.endswith("_fr") else "en"

        # Adapter la réponse à la langue détectée
        intention_reponse = meilleure_intention

        if langue == "fr" and meilleure_intention.endswith("_en"):
            intention_fr = meilleure_intention[:-3] + "_fr"

            if intention_fr in SOCIAL_RESPONSES:
                intention_reponse = intention_fr

        elif langue == "en" and meilleure_intention.endswith("_fr"):
            intention_en = meilleure_intention[:-3] + "_en"

            if intention_en in SOCIAL_RESPONSES:
                intention_reponse = intention_en

        return (
            SOCIAL_RESPONSES[intention_reponse],
            vecteur_question,
            embedding_time,
            intention_reponse,
        )

    # Aucune intention sociale suffisamment convaincante :
    # poursuivre le traitement RAG avec l'embedding déjà calculé.
    return None, vecteur_question, embedding_time, None

# ============================================================
# EXTRACTION DES TERMES SIGNIFICATIFS
# ============================================================
STOPWORDS = {
    # ========================================================
    # FRANÇAIS
    # ========================================================

    # Articles / déterminants
    "un", "une", "des", "le", "la", "les",
    "l", "du", "de", "d",
    "au", "aux",
    "ce", "cet", "cette", "ces",
    "mon", "ma", "mes",
    "ton", "ta", "tes",
    "son", "sa", "ses",
    "notre", "nos",
    "votre", "vos",
    "leur", "leurs",
    "quel", "quelle", "quels", "quelles",
    "tel", "telle", "tels", "telles",

    # Pronoms personnels
    "je", "j", "tu", "il", "elle", "on",
    "nous", "vous", "ils", "elles",
    "me", "m", "te", "t", "se", "s",
    "lui", "eux",
    "y", "en",

    # Pronoms / déterminants relatifs
    "qui", "que", "quoi",
    "dont", "où",
    "lequel", "laquelle",
    "lesquels", "lesquelles",
    "auquel", "auxquels",
    "auxquelles",
    "duquel", "desquels",
    "desquelles",

    # Pronoms indéfinis
    "on", "chacun", "chacune",
    "quelqu", "quelquun", "quelqu'une",
    "quelque", "quelques",
    "certain", "certaine", "certains", "certaines",
    "aucun", "aucune",
    "autre", "autres",
    "même", "mêmes",
    "tout", "toute", "tous", "toutes",
    "tel", "telle", "tels", "telles",

    # Auxiliaires / verbes très fréquents
    "être", "est", "es", "suis", "sommes", "êtes", "sont",
    "avoir", "ai", "as", "a", "avons", "avez", "ont",
    "faire", "fait", "fais", "font",
    "aller", "vais", "vas", "va", "allons", "allez", "vont",
    "pouvoir", "peut", "peux", "pouvez", "peuvent",
    "devoir", "dois", "doit", "devons", "devez", "doivent",
    "vouloir", "veux", "veut", "voulons", "voulez", "veulent",
    "falloir", "faut",
    "savoir", "sais", "sait", "savons", "savez", "savent",
    "dire", "dit", "dis", "disons", "dites", "disent",
    "voir", "vois", "voit", "voyons", "voyez", "voient",
    "venir", "viens", "vient", "venons", "venez", "viennent",
    "mettre", "mets", "met", "mettons", "mettez", "mettent",
    "prendre", "prends", "prend", "prenons", "prenez", "prennent",
    "donner", "donne", "donnes", "donnons", "donnez", "donnent",
    "tenir", "tiens", "tient", "tenons", "tenez", "tiennent",
    "parler", "parle", "parles", "parlons", "parlez", "parlent",
    "trouver", "trouve", "trouves", "trouvons", "trouvez", "trouvent",
    "fallu",

    # Prépositions
    "à", "a", "après", "avant",
    "avec", "chez", "contre",
    "dans", "de", "depuis",
    "derrière", "dès",
    "devant", "durant",
    "entre", "en",
    "hors", "jusque",
    "malgré", "par",
    "pendant", "pour",
    "sans", "sauf",
    "selon", "sous",
    "sur", "vers",
    "via",

    # Conjonctions
    "et", "ou", "mais", "donc",
    "or", "ni", "car",
    "comme", "ainsi",
    "lorsque", "lorsqu",
    "puisque", "puisqu",
    "quoique",
    "bien", "que",
    "si", "s", "quand",
    "tandis", "tandisque",
    "alors", "alorsque",
    "parce", "puis",

    # Mots interrogatifs
    "qui", "que", "quoi",
    "quel", "quelle", "quels", "quelles",
    "comment",
    "pourquoi",
    "quand",
    "où",
    "combien",
    "lequel", "laquelle",
    "lesquels", "lesquelles",

    # Adverbes fréquents
    "très", "trop", "plus", "moins",
    "beaucoup", "peu",
    "encore", "déjà",
    "toujours", "jamais",
    "souvent", "parfois",
    "ainsi", "aussi",
    "bien", "mal",
    "ici", "là",
    "maintenant", "alors",
    "ensuite", "puis",
    "presque", "surtout",
    "seulement",
    "simplement",
    "vraiment",
    "peut-être",
    "également",
    "notamment",
    "enfin",
    "ailleurs",
    "autrement",
    "ensemble",
    "davantage",
    "moins",

    # Négation
    "ne", "n", "pas",
    "plus", "jamais",
    "rien", "personne",
    "aucun", "aucune",
    "ni",

    # Expressions / formes contractées fréquentes
    "c", "ce", "c'est",
    "d", "l", "j", "m",
    "n", "qu", "s",
    "t", "y",
    "cette",
    "ça", "cela", "ceci",

    # ========================================================
    # ENGLISH
    # ========================================================

    # Articles / determiners
    "a", "an", "the",
    "this", "that",
    "these", "those",
    "some", "any",
    "each", "every",
    "either", "neither",
    "another", "other",
    "such",

    # Personal pronouns
    "i", "you", "he", "she", "it",
    "we", "they",
    "me", "him", "her",
    "us", "them",
    "my", "your", "his", "its",
    "our", "their",
    "mine", "yours", "hers",
    "ours", "theirs",
    "myself", "yourself", "himself",
    "herself", "itself", "ourselves",
    "yourselves", "themselves",

    # Relative / interrogative
    "who", "whom", "whose",
    "which", "what",
    "where", "when",
    "why", "how",
    "whatever", "whoever",
    "whichever",

    # Auxiliary / modal verbs
    "be", "am", "is", "are",
    "was", "were", "been", "being",
    "have", "has", "had",
    "having",
    "do", "does", "did",
    "doing",
    "can", "could",
    "may", "might",
    "must",
    "shall", "should",
    "will", "would",

    # Common verbs
    "get", "gets", "got",
    "go", "goes", "went", "going",
    "make", "makes", "made",
    "take", "takes", "took",
    "come", "comes", "came",
    "know", "knows", "knew",
    "think", "thinks", "thought",
    "see", "sees", "saw",
    "want", "wants", "wanted",
    "use", "uses", "used",
    "find", "finds", "found",
    "give", "gives", "gave",
    "tell", "tells", "told",
    "say", "says", "said",
    "look", "looks", "looked",
    "seem", "seems", "seemed",
    "try", "tries", "tried",
    "need", "needs", "needed",
    "work", "works", "worked",
    "let", "lets",
    "help", "helps", "helped",
    "show", "shows", "showed",

    # Prepositions
    "about", "above", "across",
    "after", "against", "along",
    "among", "around", "at",
    "before", "behind", "below",
    "beneath", "beside", "between",
    "beyond", "by",
    "despite", "down",
    "during",
    "except",
    "for", "from",
    "in", "inside", "into",
    "near", "of", "off",
    "on", "onto",
    "over", "past",
    "since",
    "through", "throughout",
    "to", "toward", "under",
    "until", "up",
    "upon", "with",
    "within", "without",
    "via",

    # Conjunctions
    "and", "or", "but",
    "nor", "for", "yet",
    "so",
    "although", "though",
    "because", "since",
    "unless", "while",
    "whereas", "whether",
    "if", "than",
    "that",

    # Frequent adverbs
    "very", "too", "more", "most",
    "less", "least",
    "also", "just",
    "only", "even",
    "still", "already",
    "always", "never",
    "often", "sometimes",
    "usually",
    "really", "quite",
    "rather", "almost",
    "again", "then",
    "now", "here", "there",
    "well", "ever",
    "together", "perhaps",
    "maybe",
    "especially",
    "simply",
    "actually",
    "already",
    "finally",

    # Negation
    "no", "not",
    "never", "none",
    "nothing", "nobody",
    "neither", "nowhere",

    # Other frequent terms
    "yes", "okay",
    "ok",
}


def extraire_termes_significatifs(
    texte: str
) -> set[str]:

    texte = normaliser_texte(texte)

    mots = re.findall(
        r"[a-z0-9_]+",
        texte
    )

    termes = {
        mot
        for mot in mots
        if len(mot) >= MIN_TERM_LENGTH
        and mot not in STOPWORDS
    }

    return termes

# ============================================================
# REFORMULATION
# ============================================================

async def reformuler_question(
    nouvelle_question: str,
    historique: list[Message]
) -> str:

    # --------------------------------------------------------
    # Aucun historique = aucune génération supplémentaire
    # --------------------------------------------------------

    if not historique:
        return nouvelle_question

    historique_texte = "\n".join(
        [
            f"{msg.role}: {msg.content}"
            for msg in historique[-4:]
        ]
    )

    prompt = f"""
Historique :
{historique_texte}

Nouvelle question :
{nouvelle_question}

Reformule uniquement la nouvelle question afin qu'elle
soit autonome pour une recherche documentaire.

Ne réponds pas à la question.
Ne rajoute aucune information.
""".strip()

    if ollama_client is None:
        return nouvelle_question

    response = await ollama_client.chat(
        model=OLLAMA_MODEL,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        options={
            "temperature": 0.0,
            "num_ctx": 1024,
            "num_thread": OLLAMA_NUM_THREAD,
        },
    )

    return (
        response["message"]["content"]
        .strip()
        .strip('"')
    )


# ============================================================
# RECHERCHE QDRANT
# ============================================================

async def rechercher_documents(
    search_query: str,
    question_embedding=None,
    precomputed_embedding_time: Optional[float] = None,
) -> tuple[list, float, float]:

    # --------------------------------------------------------
    # Embedding : calcul ou réutilisation du vecteur existant
    # --------------------------------------------------------

    if question_embedding is None:
        start = time.perf_counter()

        question_embedding = await asyncio.to_thread(
            models["embedding"].encode,
            search_query,
            normalize_embeddings=True,
        )

        embedding_time = time.perf_counter() - start
    else:
        embedding_time = precomputed_embedding_time or 0.0

    # Qdrant attend un vecteur Python
    if hasattr(question_embedding, "tolist"):
        question_embedding = question_embedding.tolist()

    # --------------------------------------------------------
    # Qdrant
    # --------------------------------------------------------

    start = time.perf_counter()

    results = await asyncio.to_thread(
        models["qdrant"].query_points,
        collection_name=COLLECTION_NAME,
        query=question_embedding,
        limit=RETRIEVAL_LIMIT,
        with_payload=True,
    )

    qdrant_time = time.perf_counter() - start

    return (
        results.points,
        embedding_time,
        qdrant_time,
    )


def reranker_sort(
    candidates: list,
    search_query: str,
    include_scores: bool = False,
) -> list:
    if not candidates:
        return []

    scores = models["reranker"].predict(
        [
            [search_query, result.payload.get("text", "")]
            for result in candidates
        ],
        batch_size=8,
        show_progress_bar=False,
    )
    ranked = sorted(
        zip(candidates, scores),
        key=lambda item: float(item[1]),
        reverse=True,
    )
    if include_scores:
        return [(result, float(score)) for result, score in ranked]
    return [result for result, _ in ranked]


# ============================================================
# CONTRÔLE DE PERTINENCE
# ============================================================

def verifier_pertinence(
    question: str,
    candidats: list
) -> tuple[bool, float, set[str], set[str]]:

    if not candidats:
        return False, 0.0, set(), set()

    best_score = max(float(result.score) for result in candidats)

    question_terms = (
        extraire_termes_significatifs(question)
    )

    texte_recupere = " ".join(
        result.payload.get("text", "")
        for result in candidats[:FINAL_LIMIT]
    )

    contexte_terms = (
        extraire_termes_significatifs(
            texte_recupere
        )
    )

    termes_communs = (
        question_terms
        & contexte_terms
    )

    # --------------------------------------------------------
    # CAS 1 : score insuffisant
    # --------------------------------------------------------

    if best_score < MIN_QDRANT_SCORE:
        return (
            False,
            best_score,
            question_terms,
            termes_communs,
        )

    # --------------------------------------------------------
    # CAS 2 : question ne partage absolument aucun
    # terme significatif avec les extraits
    #
    # Exemple :
    # "who is hani zitout"
    #
    # Si "hani" et "zitout" ne figurent pas dans
    # les extraits, le modèle ne doit pas improviser.
    # --------------------------------------------------------

    if (
        question_terms
        and not termes_communs
    ):
        return (
            False,
            best_score,
            question_terms,
            termes_communs,
        )

    return (
        True,
        best_score,
        question_terms,
        termes_communs,
    )


# ============================================================
# CONSTRUCTION DU CONTEXTE
# ============================================================

def construire_contexte(
    candidats: list
) -> tuple[str, list[dict], list[dict]]:

    context_parts = []
    sources_utilisees = []
    context_items = []

    total_chars = 0

    for i, result in enumerate(
        candidats[:FINAL_LIMIT]
    ):

        texte = result.payload.get(
            "text",
            ""
        )

        # ----------------------------------------------------
        # Limitation de chaque chunk
        # ----------------------------------------------------

        texte = texte[:MAX_CHARS_PER_CHUNK]

        # ----------------------------------------------------
        # Limitation globale du contexte
        # ----------------------------------------------------

        remaining = (
            MAX_CONTEXT_CHARS
            - total_chars
        )

        if remaining <= 0:
            break

        texte = texte[:remaining]

        doc_nom = result.payload.get(
            "document",
            "Inconnu"
        )

        page = result.payload.get(
            "page",
            "?"
        )

        context_parts.append(
            f"--- Extrait {i + 1} ---\n"
            f"{texte}"
        )
        context_items.append(
            {
                "rank": i + 1,
                "document": doc_nom,
                "page": page,
                "vector_score": round(float(result.score), 4),
                "text": texte,
            }
        )

        sources_utilisees.append(
            {
                "document": doc_nom,
                "page": page,
                "url": (
                    f"{os.getenv('PUBLIC_API_BASE_URL', 'http://localhost:8080').rstrip('/')}"
                    f"/documents/{quote(str(doc_nom), safe='')}#page={page}"
                ),
                "extrait": texte[:600],
                "score": round(float(result.score), 4),
            }
        )

        total_chars += len(texte)

    context_str = "\n\n".join(
        context_parts
    )

    return (
        context_str,
        sources_utilisees,
        context_items,
    )


def _deduplicate_sources(sources: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for source in sources:
        key = (source["document"], str(source["page"]))
        if key not in seen:
            seen.add(key)
            unique.append(source)
    return unique


def _record_xai_trace(
    trace: dict | None,
    status: str,
    answer: str | None = None,
    error: str | None = None,
) -> None:
    try:
        write_xai_trace(trace, status, answer, error)
    except OSError as write_error:
        print(f"Échec d’écriture de la trace XAI : {write_error}")


# ============================================================
# LOG DES RESULTATS
# ============================================================

def afficher_resultats(
    candidats: list
) -> None:
    if not DEBUG_CONTENT_LOGS:
        return

    print()
    print("📚 RÉSULTATS QDRANT")

    for i, result in enumerate(
        candidats
    ):

        score = float(
            result.score
        )

        doc = result.payload.get(
            "document",
            "Inconnu"
        )

        page = result.payload.get(
            "page",
            "?"
        )

        texte = result.payload.get(
            "text",
            ""
        )

        # Pour le diagnostic seulement :
        # on affiche les premiers caractères.
        preview = (
            texte
            .replace("\n", " ")
            .strip()
        )[:250]

        print(
            f"   [{i + 1}] "
            f"score={score:.4f} "
            f"| {doc} "
            f"| page={page}"
        )

        print(
            f"       {preview}..."
        )


# ============================================================
# CONSTRUCTION DES MESSAGES OLLAMA
# ============================================================

def construire_messages(
    question: str,
    historique: list[Message],
    context_str: str,
) -> list[dict]:

    prompt_systeme = (
        f"{SYSTEM_PROMPT}\n\n"
        f"EXTRAITS DE LA DOCUMENTATION :\n"
        f"{context_str}"
    )

    messages = [
        {
            "role": "system",
            "content": prompt_systeme,
        }
    ]

    # --------------------------------------------------------
    # On limite aussi l'historique pour éviter
    # que le prompt grossisse indéfiniment.
    # --------------------------------------------------------

    for msg in historique[-4:]:

        messages.append(
            {
                "role": msg.role,
                "content": msg.content,
            }
        )

    messages.append(
        {
            "role": "user",
            "content": question,
        }
    )

    return messages


# ============================================================
# PIPELINE RAG COMMUN
# ============================================================

async def preparer_reponse(
    request: ChatRequest
) -> dict:

    total_start = time.perf_counter()

    request_id = generate_request_id()

    print()
    print("=" * 60)
    print("🔎 NOUVELLE REQUÊTE")
    print("=" * 60)

    print(
        f"🆔 Request ID : {request_id}"
    )

    if DEBUG_CONTENT_LOGS:
        print(f"❓ Question : {request.question}")

    # --------------------------------------------------------
    # 0. Routage conversationnel avant le RAG
    # --------------------------------------------------------

    (
        social_response,
        routing_embedding,
        routing_embedding_time,
        social_intent,
    ) = await asyncio.to_thread(
        detecter_intention_sociale,
        request.question,
    )

    if social_response is not None:

        elapsed = time.perf_counter() - total_start

        print(
            f"💬 Réponse directe : {social_intent}"
        )
        print(
            f"⏱️ Temps avant réponse : {elapsed:.2f}s"
        )

        write_audit_log(
            create_audit_event(
                question=request.question,
                request_id=request_id,
                status="social_response",
                results_count=0,
                best_score=0.0,
                reformulation_seconds=0.0,
                embedding_seconds=routing_embedding_time,
                qdrant_seconds=0.0,
                context_seconds=0.0,
                time_before_ollama_seconds=0.0,
                total_seconds=elapsed,
            )
        )

        return {
            "autorise": False,
            "reponse": social_response,
            "sources": [],
            "score_confiance": 0.0,
            "messages": [],
            "total_avant_ollama": elapsed,
            "request_id": request_id,
            "xai_trace": {
                "request_id": request_id,
                "question": request.question,
                "conversation_history": [
                    {"role": message.role, "content": message.content}
                    for message in request.historique[-4:]
                ],
                "search_query": None,
                "retrieval_path": [],
                "selected_context": [],
                "final_sources": [],
                "graph_context": {
                    "available": False,
                    "reason": "La requête a été traitée sans recherche documentaire.",
                },
            },
        }

    # --------------------------------------------------------
    # 1. Reformulation
    # --------------------------------------------------------

    start = time.perf_counter()

    search_query = await reformuler_question(
        request.question,
        request.historique,
    )

    reformulation_time = (
        time.perf_counter() - start
    )

    print(
        f"⏱️ Reformulation : "
        f"{reformulation_time:.2f}s"
    )

    if DEBUG_CONTENT_LOGS:
        print(f"🔍 Requête de recherche : {search_query}")

    # --------------------------------------------------------
    # 2 + 3. Embedding + Qdrant
    # --------------------------------------------------------

    # Réutiliser le vecteur si la question n'a pas été reformulée.
    vecteur_reutilisable = (
        routing_embedding
        if search_query == request.question
        else None
    )

    temps_vecteur_reutilisable = (
        routing_embedding_time
        if vecteur_reutilisable is not None
        else None
    )

    candidats, embedding_time, qdrant_time = await rechercher_documents(
        search_query,
        question_embedding=vecteur_reutilisable,
        precomputed_embedding_time=temps_vecteur_reutilisable,
    )

    retrieved_candidates = [
        {
            "rank": index,
            "document": result.payload.get("document", "Inconnu"),
            "page": result.payload.get("page", "?"),
            "vector_score": round(float(result.score), 4),
            "text_preview": result.payload.get("text", "")[:300],
        }
        for index, result in enumerate(candidats, start=1)
    ]
    candidats = apply_document_exclusions(
        candidats,
        EXCLUDED_DOCUMENTS,
    )
    excluded_candidates = [
        item
        for item in retrieved_candidates
        if item["document"] in EXCLUDED_DOCUMENTS
    ]

    rerank_start = time.perf_counter()
    reranked_candidates = await asyncio.to_thread(
        reranker_sort,
        candidats,
        search_query,
        True,
    )
    candidats = [result for result, _ in reranked_candidates]
    rerank_time = time.perf_counter() - rerank_start
    reranked_trace = [
        {
            "rank": index,
            "document": result.payload.get("document", "Inconnu"),
            "page": result.payload.get("page", "?"),
            "vector_score": round(float(result.score), 4),
            "reranker_score": round(reranker_score, 4),
            "text_preview": result.payload.get("text", "")[:300],
        }
        for index, (result, reranker_score) in enumerate(
            reranked_candidates,
            start=1,
        )
    ]

    # Si l'historique a conduit à une reformulation, le détecteur
    # a calculé un premier embedding qui n'a pas été réutilisé.

    print(
        f"⏱️ Embedding : "
        f"{embedding_time:.2f}s"
    )

    print(
        f"⏱️ Qdrant : "
        f"{qdrant_time:.2f}s"
    )

    print(
        f"📚 Résultats récupérés : "
        f"{len(candidats)}"
    )
    print(f"⏱️ Reranking : {rerank_time:.2f}s")

    # --------------------------------------------------------
    # Aucun résultat
    # --------------------------------------------------------

    if not candidats:

        print(
            "🚫 Aucun résultat documentaire."
        )

        write_audit_log(
            create_audit_event(
                question=request.question,
                request_id=request_id,
                status="no_results",
                results_count=0,
                best_score=0.0,
                reformulation_seconds=reformulation_time,
                embedding_seconds=embedding_time,
                qdrant_seconds=qdrant_time,
                total_seconds=(
                    time.perf_counter()
                    - total_start
                ),
            )
        )

        return {
            "autorise": False,
            "reponse": REFUS_MESSAGE,
            "sources": [],
            "score_confiance": 0.0,
            "messages": [],
            "total_avant_ollama": (
                time.perf_counter()
                - total_start
            ),
            "request_id": request_id,
            "xai_trace": {
                "request_id": request_id,
                "question": request.question,
                "conversation_history": [
                    {"role": message.role, "content": message.content}
                    for message in request.historique[-4:]
                ],
                "search_query": search_query,
                "retrieval_path": retrieved_candidates,
                "excluded_candidates": excluded_candidates,
                "reranked_candidates": reranked_trace,
                "selected_context": [],
                "final_sources": [],
                "graph_context": {
                    "available": False,
                    "reason": "Aucun graphe de connaissances n’est connecté au pipeline.",
                },
            },
        }

    # --------------------------------------------------------
    # Diagnostic résultats
    # --------------------------------------------------------

    afficher_resultats(
        candidats
    )

    # --------------------------------------------------------
    # 4. Guardrail
    # --------------------------------------------------------


    autorise, best_score, question_terms, termes_communs = (
        verifier_pertinence(
            search_query,
            candidats,
        )
    )


    print(
        f"🎯 Meilleur score Qdrant : "
        f"{best_score:.4f}"
    )

    if DEBUG_CONTENT_LOGS:
        print(f"🔑 Termes question : {sorted(question_terms)}")
        print(
            "✅ Termes trouvés dans les extraits : "
            f"{sorted(termes_communs)}"
        )

    if not autorise:

        print(
            "🚫 GUARDRAIL : "
            "les extraits ne sont pas suffisamment "
            "liés à la question."
        )

        write_audit_log(
            create_audit_event(
                question=request.question,
                request_id=request_id,
                status="guardrail_blocked",
                results_count=len(candidats),
                best_score=best_score,
                reformulation_seconds=reformulation_time,
                embedding_seconds=embedding_time,
                qdrant_seconds=qdrant_time,
                total_seconds=(
                    time.perf_counter()
                    - total_start
                ),
            )
        )

        return {
            "autorise": False,
            "reponse": REFUS_MESSAGE,
            "sources": [],
            "score_confiance": round(
                best_score,
                4
            ),
            "messages": [],
            "total_avant_ollama": (
                time.perf_counter()
                - total_start
            ),
            "request_id": request_id,
            "xai_trace": {
                "request_id": request_id,
                "question": request.question,
                "conversation_history": [
                    {"role": message.role, "content": message.content}
                    for message in request.historique[-4:]
                ],
                "search_query": search_query,
                "retrieval_path": retrieved_candidates,
                "excluded_candidates": excluded_candidates,
                "reranked_candidates": reranked_trace,
                "selected_context": [],
                "final_sources": [],
                "guardrail": {
                    "allowed": False,
                    "best_vector_score": round(best_score, 4),
                    "question_terms": sorted(question_terms),
                    "shared_terms": sorted(termes_communs),
                },
                "graph_context": {
                    "available": False,
                    "reason": "Aucun graphe de connaissances n’est connecté au pipeline.",
                },
            },
        }

    # --------------------------------------------------------
    # 5. Contexte
    # --------------------------------------------------------

    start = time.perf_counter()

    context_str, sources_utilisees, context_items = (
        construire_contexte(
            candidats
        )
    )

    context_time = (
        time.perf_counter() - start
    )

    print(
        f"⏱️ Construction contexte : "
        f"{context_time:.2f}s"
    )

    # --------------------------------------------------------
    # Diagnostic contexte
    # --------------------------------------------------------

    print()
    print("📊 DIAGNOSTIC DU CONTEXTE")

    print(
        f"   Caractères contexte : "
        f"{len(context_str):,}"
    )

    print(
        f"   Mots contexte       : "
        f"{len(context_str.split()):,}"
    )

    print(
        f"   Tokens approximatifs: "
        f"{len(context_str) / 4:,.0f}"
    )

    # --------------------------------------------------------
    # 6. Messages
    # --------------------------------------------------------

    messages_llm = construire_messages(
        question=request.question,
        historique=request.historique,
        context_str=context_str,
    )

    total_prompt_chars = sum(
        len(message["content"])
        for message in messages_llm
    )

    print(
        f"📊 Taille totale prompt : "
        f"{total_prompt_chars:,} caractères"
    )

    print(
        f"📊 Tokens approximatifs : "
        f"{total_prompt_chars / 4:,.0f}"
    )

    # --------------------------------------------------------
    # Temps total avant Ollama
    # --------------------------------------------------------

    before_ollama = (
        time.perf_counter()
        - total_start
    )

    print()
    print(
        f"⏱️ TEMPS TOTAL AVANT OLLAMA : "
        f"{before_ollama:.2f}s"
    )

    # --------------------------------------------------------
    # Préparation des sources d'audit
    # --------------------------------------------------------

    sources_audit = []

    for result in candidats[:FINAL_LIMIT]:

        sources_audit.append(
            {
                "document": result.payload.get(
                    "document",
                    "Inconnu"
                ),
                "page": result.payload.get(
                    "page",
                    "?"
                ),
                "score": round(
                    float(result.score),
                    4
                ),
            }
        )

    cited_sources = _deduplicate_sources(sources_utilisees)
    xai_trace = {
        "request_id": request_id,
        "question": request.question,
        "conversation_history": [
            {"role": message.role, "content": message.content}
            for message in request.historique[-4:]
        ],
        "search_query": search_query,
        "retrieval_limit": RETRIEVAL_LIMIT,
        "excluded_documents": sorted(EXCLUDED_DOCUMENTS),
        "retrieval_path": retrieved_candidates,
        "excluded_candidates": excluded_candidates,
        "reranked_candidates": reranked_trace,
        "selected_context": context_items,
        "final_sources": cited_sources,
        "citation_provenance": citation_provenance(
            cited_sources,
            context_items,
        ),
        "guardrail": {
            "allowed": True,
            "best_vector_score": round(best_score, 4),
            "question_terms": sorted(question_terms),
            "shared_terms": sorted(termes_communs),
        },
        "graph_context": {
            "available": False,
            "reason": "Le système actuel utilise Qdrant vectoriel, sans graphe de connaissances ni parcours de relations.",
        },
        "prompt_context_characters": len(context_str),
    }

    # --------------------------------------------------------
    # Retour vers le streaming
    # --------------------------------------------------------

    return {
        "autorise": True,
        "reponse": "",
        "sources": cited_sources,
        "sources_audit": sources_audit,
        "xai_trace": xai_trace,
        "score_confiance": round(
            best_score,
            4
        ),
        "messages": messages_llm,

        "request_id": request_id,

        "reformulation_time": reformulation_time,
        "embedding_time": embedding_time,
        "qdrant_time": qdrant_time,
        "rerank_time": rerank_time,
        "context_time": context_time,
        "before_ollama": before_ollama,

        "total_avant_ollama": before_ollama,
    }

# ============================================================
# STREAMING
# ============================================================

async def generate_stream(
    request: ChatRequest
) -> AsyncGenerator[str, None]:

    prepared = await preparer_reponse(
        request
    )

    request_id = prepared["request_id"]

        # --------------------------------------------------------
        # Guardrail
        # --------------------------------------------------------

    if not prepared["autorise"]:
        _record_xai_trace(
            prepared.get("xai_trace"),
            "refused",
            answer=prepared["reponse"],
        )

        data = {
            "type": "final",
            "reponse": prepared["reponse"],
            "sources": [],
            "score_confiance": prepared[
                "score_confiance"
            ],
            "request_id": request_id,
        }

        yield (
            "data: "
            + json.dumps(
                data,
                ensure_ascii=False
            )
            + "\n\n"
        )

        return

    messages_llm = prepared[
        "messages"
    ]

    sources = prepared[
        "sources"
    ]

    score = prepared[
        "score_confiance"
    ]

    print(
        "🤖 Démarrage du streaming Ollama..."
    )

    ollama_start = time.perf_counter()
    first_token_received = False
    ollama_first_token = None
    full_response = ""

    try:

        if ollama_client is None:
            raise RuntimeError(
                "Client Ollama non initialisé."
            )

        stream = await ollama_client.chat(
            model=OLLAMA_MODEL,
            messages=messages_llm,
            stream=True,
            options={
                "temperature": OLLAMA_TEMPERATURE,
                "num_ctx": OLLAMA_NUM_CTX,
                "num_thread": OLLAMA_NUM_THREAD,
            },
        )

        async for chunk in stream:

            token = chunk[
                "message"
            ]["content"]

            # ------------------------------------------------
            # Premier token
            # ------------------------------------------------

            if not first_token_received:

                first_token_received = True

                ollama_first_token = (
                    time.perf_counter()
                    - ollama_start
                )

                total_first_token = (
                    prepared["total_avant_ollama"]
                    + ollama_first_token
                )

                print()
                print(
                    f"🚀 PREMIER TOKEN "
                    f"Ollama : "
                    f"{ollama_first_token:.2f}s "
                    f"après l'appel"
                )

                print(
                    f"⏱️ TOTAL JUSQU'AU PREMIER TOKEN : "
                    f"{total_first_token:.2f}s"
                )

            # ------------------------------------------------
            # Token
            # ------------------------------------------------

            full_response += token

            data = {
                "type": "token",
                "content": token,
            }

            yield (
                "data: "
                + json.dumps(
                    data,
                    ensure_ascii=False
                )
                + "\n\n"
            )

            # ----------------------------------------------------
            # Fin génération
            # ----------------------------------------------------

        generation_time = (
            time.perf_counter()
            - ollama_start
        )

        total_time = (
            prepared["total_avant_ollama"]
            + generation_time
        )

        print()
        print(
            f"⏱️ Génération Ollama : "
            f"{generation_time:.2f}s"
        )

        print(
            f"🏁 TEMPS TOTAL ESTIMÉ : "
            f"{total_time:.2f}s"
        )

        print("=" * 60)
        print()

        write_audit_log(
            create_audit_event(
                question=request.question,
                request_id=request_id,
                status="success",
                sources=prepared["sources_audit"],
                best_score=score,
                results_count=len(
                    prepared["sources_audit"]
                ),
                reformulation_seconds=prepared[
                    "reformulation_time"
                ],
                embedding_seconds=prepared[
                    "embedding_time"
                ],
                qdrant_seconds=prepared[
                    "qdrant_time"
                ],
                rerank_seconds=prepared["rerank_time"],
                context_seconds=prepared[
                    "context_time"
                ],
                time_before_ollama_seconds=prepared[
                    "before_ollama"
                ],
                ollama_first_token_seconds=ollama_first_token,
                ollama_generation_seconds=generation_time,
                total_seconds=total_time,
            )
        )
        _record_xai_trace(
            prepared.get("xai_trace"),
            "success",
            answer=full_response,
        )

            # ----------------------------------------------------
            # Réponse finale
            # ----------------------------------------------------

        final_data = {
            "type": "final",
            "reponse": full_response,
            "sources": sources,
            "score_confiance": score,
            "request_id": request_id,
        }

        yield (
            "data: "
            + json.dumps(
                final_data,
                ensure_ascii=False
            )
            + "\n\n"
        )

    except Exception as e:

        print(
            f"❌ ERREUR OLLAMA : {e}"
        )
        _record_xai_trace(
            prepared.get("xai_trace"),
            "error",
            answer=full_response or None,
            error=str(e),
        )

        error_data = {
            "type": "error",
            "content": "Une erreur interne est survenue pendant la génération.",
        }

        yield (
            "data: "
            + json.dumps(
                error_data,
                ensure_ascii=False
            )
            + "\n\n"
        )


@app.post("/feedback")
async def save_feedback(request: FeedbackRequest):
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": request.request_id,
        "rating": request.rating,
    }
    feedback_file = AUDIT_DIR / "feedback.jsonl"
    with feedback_lock:
        with feedback_file.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")
    return {"ok": True}


@app.post("/admin/documents")
async def upload_document(
    file: UploadFile = File(...),
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
):
    if not UPLOAD_ADMIN_KEY:
        raise HTTPException(
            status_code=503,
            detail="L’import est désactivé : configurez RSLM_ADMIN_KEY sur l’API.",
        )
    if not x_admin_key or not hmac.compare_digest(
        x_admin_key,
        UPLOAD_ADMIN_KEY,
    ):
        raise HTTPException(status_code=403, detail="Clé administrateur invalide.")

    original_name = file.filename or ""
    safe_name = PurePosixPath(original_name.replace("\\", "/")).name
    if not safe_name or safe_name in {".", ".."}:
        raise HTTPException(status_code=400, detail="Nom de fichier invalide.")
    if not safe_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Seuls les fichiers PDF sont acceptés.")

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Le PDF dépasse la limite de 25 Mo.")
    if not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail="Le fichier fourni n’est pas un PDF valide.")

    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    target = DOCUMENTS_DIR / safe_name

    async with upload_lock:
        if target.exists():
            raise HTTPException(
                status_code=409,
                detail="Un document portant ce nom existe déjà.",
            )
        target.write_bytes(content)
        try:
            async with REQUEST_SEMAPHORE:
                count = await asyncio.to_thread(
                    index_pdf,
                    target,
                    models["embedding"],
                    models["qdrant"],
                )
        except ValueError as error:
            target.unlink(missing_ok=True)
            print(f"PDF non indexable {safe_name}: {error}")
            raise HTTPException(
                status_code=422,
                detail="Le PDF est invalide ou ne peut pas être indexé.",
            ) from error
        except Exception as error:
            target.unlink(missing_ok=True)
            print(f"Échec d’indexation de {safe_name}: {error}")
            raise HTTPException(
                status_code=500,
                detail="L’indexation du PDF a échoué ; le fichier n’a pas été conservé.",
            ) from error

    return {"document": safe_name, "chunks_indexed": count}


def _require_admin_key(provided_key: str | None) -> None:
    if not UPLOAD_ADMIN_KEY:
        raise HTTPException(
            status_code=503,
            detail="L’administration est désactivée : configurez RSLM_ADMIN_KEY sur l’API.",
        )
    if not provided_key or not hmac.compare_digest(
        provided_key,
        UPLOAD_ADMIN_KEY,
    ):
        raise HTTPException(status_code=403, detail="Clé administrateur invalide.")


def _validated_document_name(document: str) -> str:
    safe_name = PurePosixPath(document.replace("\\", "/")).name
    if safe_name != document or safe_name in {"", ".", ".."}:
        raise HTTPException(status_code=400, detail="Nom de document invalide.")
    if not safe_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Seuls les fichiers PDF sont acceptés.")
    return safe_name


@app.get("/admin/documents")
async def list_documents(
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
):
    _require_admin_key(x_admin_key)
    counts = await asyncio.to_thread(
        count_document_points,
        models["qdrant"],
    )
    documents = []
    for path in sorted(DOCUMENTS_DIR.glob("*.pdf"), key=lambda item: item.name.lower()):
        stat = path.stat()
        chunk_count = counts.pop(path.name, 0)
        documents.append(
            {
                "document": path.name,
                "status": "indexed" if chunk_count else "not_indexed",
                "chunks_indexed": chunk_count,
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(
                    stat.st_mtime,
                    timezone.utc,
                ).isoformat(),
            }
        )
    documents.extend(
        {
            "document": name,
            "status": "file_missing",
            "chunks_indexed": chunk_count,
            "size_bytes": None,
            "modified_at": None,
        }
        for name, chunk_count in sorted(counts.items())
    )
    return {"documents": documents}


@app.get("/admin/backups/documents")
async def get_document_backups(
    document: str | None = None,
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
):
    _require_admin_key(x_admin_key)
    if document is not None:
        document = _validated_document_name(document)
    return {
        "backups": await asyncio.to_thread(
            list_document_backups,
            BACKUP_DIR,
            document,
        )
    }


@app.post("/admin/documents/{document}/reindex")
async def reindex_document(
    document: str,
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
):
    _require_admin_key(x_admin_key)
    safe_name = _validated_document_name(document)
    target = DOCUMENTS_DIR / safe_name
    if not target.is_file():
        raise HTTPException(status_code=404, detail="PDF introuvable dans le corpus.")

    async with upload_lock:
        backup = await asyncio.to_thread(
            create_document_backup,
            target,
            EMBEDDINGS_FILE,
            models["qdrant"],
            BACKUP_DIR,
        )
        try:
            async with REQUEST_SEMAPHORE:
                count = await asyncio.to_thread(
                    index_pdf,
                    target,
                    models["embedding"],
                    models["qdrant"],
                )
        except ValueError as error:
            try:
                await asyncio.to_thread(
                    restore_document_backup,
                    backup["id"],
                    target,
                    EMBEDDINGS_FILE,
                    models["qdrant"],
                    BACKUP_DIR,
                )
            except Exception as restore_error:
                print(
                    f"Échec de restauration après réindexation de "
                    f"{safe_name}: {restore_error}"
                )
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "La réindexation a échoué et la restauration "
                        "automatique a aussi échoué. "
                        f"Sauvegarde conservée ({backup['id']})."
                    ),
                ) from error
            raise HTTPException(
                status_code=422,
                detail="Le PDF est invalide ou ne peut pas être indexé.",
            ) from error
        except Exception as error:
            print(f"Échec de réindexation de {safe_name}: {error}")
            try:
                await asyncio.to_thread(
                    restore_document_backup,
                    backup["id"],
                    target,
                    EMBEDDINGS_FILE,
                    models["qdrant"],
                    BACKUP_DIR,
                )
            except Exception as restore_error:
                print(
                    f"Échec de restauration après réindexation de "
                    f"{safe_name}: {restore_error}"
                )
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "La réindexation et la restauration automatique ont "
                        f"échoué. Sauvegarde conservée ({backup['id']})."
                    ),
                ) from error
            raise HTTPException(
                status_code=500,
                detail=(
                    "La réindexation a échoué ; l’index précédent a été "
                    f"restauré. Sauvegarde : {backup['id']}."
                ),
            ) from error
    return {
        "document": safe_name,
        "chunks_indexed": count,
        "backup_id": backup["id"],
    }


@app.delete("/admin/documents/{document}")
async def delete_document(
    document: str,
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
):
    _require_admin_key(x_admin_key)
    safe_name = _validated_document_name(document)
    target = DOCUMENTS_DIR / safe_name

    async with upload_lock:
        backup = await asyncio.to_thread(
            create_document_backup,
            target,
            EMBEDDINGS_FILE,
            models["qdrant"],
            BACKUP_DIR,
        )
        try:
            deleted_chunks = await asyncio.to_thread(
                delete_document_points,
                models["qdrant"],
                safe_name,
            )
            await asyncio.to_thread(
                remove_document_embeddings,
                EMBEDDINGS_FILE,
                safe_name,
            )
            if target.is_file():
                await asyncio.to_thread(target.unlink)
            elif not deleted_chunks:
                raise HTTPException(
                    status_code=404,
                    detail="Document et passages introuvables dans le corpus.",
                )
        except HTTPException:
            try:
                await asyncio.to_thread(
                    restore_document_backup,
                    backup["id"],
                    target,
                    EMBEDDINGS_FILE,
                    models["qdrant"],
                    BACKUP_DIR,
                )
            except Exception as restore_error:
                print(
                    f"Échec de restauration après suppression de "
                    f"{safe_name}: {restore_error}"
                )
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "La suppression et la restauration automatique ont "
                        f"échoué. Sauvegarde conservée ({backup['id']})."
                    ),
                )
            raise
        except Exception as error:
            print(f"Échec de suppression de {safe_name}: {error}")
            try:
                await asyncio.to_thread(
                    restore_document_backup,
                    backup["id"],
                    target,
                    EMBEDDINGS_FILE,
                    models["qdrant"],
                    BACKUP_DIR,
                )
            except Exception as restore_error:
                print(
                    f"Échec de restauration après suppression de "
                    f"{safe_name}: {restore_error}"
                )
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "La suppression et la restauration automatique ont "
                        f"échoué. Sauvegarde conservée ({backup['id']})."
                    ),
                ) from error
            raise HTTPException(
                status_code=500,
                detail=(
                    "La suppression a échoué ; le document a été restauré. "
                    f"Sauvegarde : {backup['id']}."
                ),
            ) from error
    return {
        "document": safe_name,
        "chunks_deleted": deleted_chunks,
        "backup_id": backup["id"],
    }


@app.post("/admin/documents/{document}/restore/{backup_id}")
async def restore_document(
    document: str,
    backup_id: str,
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
):
    _require_admin_key(x_admin_key)
    safe_name = _validated_document_name(document)
    target = DOCUMENTS_DIR / safe_name
    async with upload_lock:
        safety_backup = await asyncio.to_thread(
            create_document_backup,
            target,
            EMBEDDINGS_FILE,
            models["qdrant"],
            BACKUP_DIR,
        )
        try:
            restored = await asyncio.to_thread(
                restore_document_backup,
                backup_id,
                target,
                EMBEDDINGS_FILE,
                models["qdrant"],
                BACKUP_DIR,
            )
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail="Sauvegarde introuvable.",
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=400,
                detail="La sauvegarde est invalide.",
            ) from error
        except Exception as error:
            try:
                await asyncio.to_thread(
                    restore_document_backup,
                    safety_backup["id"],
                    target,
                    EMBEDDINGS_FILE,
                    models["qdrant"],
                    BACKUP_DIR,
                )
            except Exception as restore_error:
                print(
                    f"Échec du retour arrière après restauration de "
                    f"{safe_name}: {restore_error}"
                )
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "La restauration et son retour arrière ont échoué. "
                        f"Sauvegarde conservée ({safety_backup['id']})."
                    ),
                ) from error
            raise HTTPException(
                status_code=500,
                detail=(
                    "La restauration a échoué ; l’état précédent a été "
                    f"rétabli. Sauvegarde : {safety_backup['id']}."
                ),
            ) from error
    return {
        "document": safe_name,
        "restored_backup_id": restored["id"],
        "safety_backup_id": safety_backup["id"],
    }


@app.get("/admin/backups/conversations")
async def get_conversation_backups(
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
):
    _require_admin_key(x_admin_key)
    return {
        "backups": await asyncio.to_thread(
            list_conversation_backups,
            BACKUP_DIR,
        )
    }


@app.post("/admin/backups/conversations")
async def backup_conversations(
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
):
    _require_admin_key(x_admin_key)
    try:
        backup = await asyncio.to_thread(
            create_conversation_backup,
            CONVERSATION_DATABASE_PATH,
            BACKUP_DIR,
        )
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail="Base de conversations introuvable.",
        ) from error
    return backup


@app.post("/admin/backups/conversations/{backup_id}/restore")
async def restore_conversations(
    backup_id: str,
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
):
    _require_admin_key(x_admin_key)
    try:
        safety_backup = await asyncio.to_thread(
            create_conversation_backup,
            CONVERSATION_DATABASE_PATH,
            BACKUP_DIR,
        )
        restored = await asyncio.to_thread(
            restore_conversation_backup,
            backup_id,
            CONVERSATION_DATABASE_PATH,
            BACKUP_DIR,
        )
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail="Sauvegarde de conversations introuvable.",
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail="La sauvegarde de conversations est invalide.",
        ) from error
    return {
        "restored_backup_id": restored["id"],
        "safety_backup_id": safety_backup["id"],
    }


# ============================================================
# ENDPOINT STREAMING
# ============================================================

@app.post("/chat/stream")
async def chat_stream_endpoint(
    request: ChatRequest
):

    return StreamingResponse(
        generate_stream_limited(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def generate_stream_limited(
    request: ChatRequest,
) -> AsyncGenerator[str, None]:
    async with REQUEST_SEMAPHORE:
        async for event in generate_stream(request):
            yield event


# ============================================================
# ENDPOINT CLASSIQUE
# ============================================================

@app.post("/chat")
async def chat_endpoint(
    request: ChatRequest,
):
    async with REQUEST_SEMAPHORE:
        prepared = await preparer_reponse(request)
        request_id = prepared["request_id"]
        if not prepared["autorise"]:
            _record_xai_trace(
                prepared.get("xai_trace"),
                "refused",
                answer=prepared["reponse"],
            )
            return {
                "reponse": prepared["reponse"],
                "sources": [],
                "score_confiance": prepared["score_confiance"],
                "request_id": request_id,
            }

        if ollama_client is None:
            _record_xai_trace(
                prepared.get("xai_trace"),
                "error",
                error="Client Ollama non initialisé.",
            )
            raise HTTPException(
                status_code=503,
                detail="Client Ollama non initialisé.",
            )
        start = time.perf_counter()
        try:
            response = await ollama_client.chat(
                model=OLLAMA_MODEL,
                messages=prepared["messages"],
                stream=False,
                options={
                    "temperature": OLLAMA_TEMPERATURE,
                    "num_ctx": OLLAMA_NUM_CTX,
                    "num_thread": OLLAMA_NUM_THREAD,
                },
            )
            generation_time = time.perf_counter() - start
            total_time = prepared["total_avant_ollama"] + generation_time
            write_audit_log(
                create_audit_event(
                    question=request.question,
                    request_id=request_id,
                    status="success",
                    sources=prepared["sources_audit"],
                    best_score=prepared["score_confiance"],
                    results_count=len(prepared["sources_audit"]),
                    reformulation_seconds=prepared["reformulation_time"],
                    embedding_seconds=prepared["embedding_time"],
                    qdrant_seconds=prepared["qdrant_time"],
                    rerank_seconds=prepared["rerank_time"],
                    context_seconds=prepared["context_time"],
                    time_before_ollama_seconds=prepared["before_ollama"],
                    ollama_first_token_seconds=None,
                    ollama_generation_seconds=generation_time,
                    total_seconds=total_time,
                )
            )
            _record_xai_trace(
                prepared.get("xai_trace"),
                "success",
                answer=response["message"]["content"],
            )
            return {
                "reponse": response["message"]["content"],
                "sources": prepared["sources"],
                "score_confiance": prepared["score_confiance"],
                "request_id": request_id,
            }
        except Exception as error:
            print(
                f"Échec du traitement du chat ({request_id}): {error}"
            )
            _record_xai_trace(
                prepared.get("xai_trace"),
                "error",
                error=str(error),
            )
            write_audit_log(
                create_audit_event(
                    question=request.question,
                    request_id=request_id,
                    status="error",
                    sources=prepared.get("sources_audit", []),
                    best_score=prepared.get("score_confiance"),
                    results_count=len(prepared.get("sources_audit", [])),
                    reformulation_seconds=prepared.get("reformulation_time"),
                    embedding_seconds=prepared.get("embedding_time"),
                    qdrant_seconds=prepared.get("qdrant_time"),
                    context_seconds=prepared.get("context_time"),
                    time_before_ollama_seconds=prepared.get("before_ollama"),
                    total_seconds=(
                        prepared.get("before_ollama", 0)
                        + time.perf_counter()
                        - start
                    ),
                )
            )
            raise HTTPException(
                status_code=500,
                detail=(
                    "Une erreur interne est survenue pendant le traitement. "
                    f"Référence : {request_id}."
                ),
            ) from error