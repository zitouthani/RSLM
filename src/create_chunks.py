from pathlib import Path
from collections import Counter
import json
import re


PROJECT_DIR = Path(__file__).resolve().parent.parent
INPUT_FILE = PROJECT_DIR / "data" / "pages.json"
OUTPUT_FILE = PROJECT_DIR / "data" / "chunks.json"


# Taille approximative maximale d'un chunk en caractères.
# Augmentée par rapport à la version précédente (3000 -> 4000) car on
# découpe désormais par section : une section qui tient dans cette
# taille reste UN SEUL chunk, donc on peut se permettre une taille un
# peu plus large sans perdre de cohérence.
CHUNK_SIZE = 5000

# Chevauchement entre deux sous-chunks, utilisé uniquement quand une
# section dépasse CHUNK_SIZE et doit être redécoupée.
OVERLAP = 300

# Nombre de lignes examinées en haut et en bas de chaque page pour
# repérer un éventuel en-tête / pied de page répété.
EDGE_LINES = 2

# Une ligne n'est considérée comme en-tête/pied de page que si elle
# revient sur au moins cette proportion des pages du document.
MIN_HEADER_FOOTER_RATIO = 0.3

# En dessous de ce nombre de pages, l'analyse de fréquence n'est pas
# fiable (pas assez d'échantillons) : on supprime alors uniquement les
# numéros de page isolés.
MIN_PAGES_FOR_HEADER_DETECTION = 5

# Une ligne de titre ne doit pas dépasser ce nombre de mots.
MAX_HEADING_WORDS = 12

# Caractères qui trahissent une ligne de code plutôt qu'un titre.
CODE_LIKE_CHARS = set("(){}=<>;")

HEADING_PREFIX_PATTERN = re.compile(
    r"^(chapitre|partie|annexe|section)\s+[\divxlcdm]+", re.IGNORECASE
)
# Numérotation classique : "3.2 Titre" OU "3.2. Titre" (point final optionnel
# avant l'espace, très courant dans les ouvrages techniques).
HEADING_NUMBERED_PATTERN = re.compile(
    r"^\d{1,3}(?:\.\d{1,3})*\.\s+\S",
    re.IGNORECASE
)
# Sous-titres du type "Phase 2 : ...", "Étape 3 : ..." : un mot capitalisé,
# un numéro, puis un deux-points. Générique (ne dépend pas du mot utilisé).
HEADING_LABELED_PATTERN = re.compile(r"^[A-ZÀ-ÖØ-Ý][a-zà-öø-ÿ]+\s+\d{1,3}\s*:\s*\S")
#Fais en sorte qu'un numéro de section isolé ne soit pas un titre.
NUMBER_ONLY_PATTERN = re.compile(
    r"^\d{1,3}(?:\.\d{1,3})+$"
)


def normalize_whitespace(text):
    """Nettoie légèrement le texte : espaces multiples, sauts de ligne multiples."""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_line_for_matching(line):
    """
    Normalise une ligne pour comparer des en-têtes/pieds de page qui ne
    diffèrent que par un numéro de page (ex: 'Chapitre 3 - 42' et
    'Chapitre 3 - 43' doivent être reconnus comme le même motif).
    """
    normalized = re.sub(r"\d+", "#", line.strip().lower())
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def is_probably_page_number(line):
    """Détecte une ligne qui ne contient qu'un numéro de page isolé."""
    stripped = line.strip()

    if not stripped:
        return False

    if re.fullmatch(r"[-–—\s]*\d{1,4}[-–—\s]*", stripped):
        return True

    if re.fullmatch(r"(?i)page\s*\d{1,4}", stripped):
        return True

    return False


def is_probable_heading(line):
    stripped = line.strip()

    # 1. Règles d'exclusion (ce qui n'est PAS un titre)
    if not stripped or len(stripped) > 100:
        return False

    if NUMBER_ONLY_PATTERN.fullmatch(stripped):
        return False

    if any(ch in CODE_LIKE_CHARS for ch in stripped):
        return False

    # 2. Règles d'inclusion (Ce qui EST un titre)
    # Détecte tes titres spécifiques : "1. Titre", "46. Configuration", etc.
    if HEADING_NUMBERED_PATTERN.match(stripped):
        return True

    if HEADING_PREFIX_PATTERN.match(stripped):
        return True

    if HEADING_LABELED_PATTERN.match(stripped):
        return True

    return False


def detect_running_headers_footers(doc_pages):
    """
    Repère les lignes qui se répètent en haut/bas d'un grand nombre de
    pages d'un même document (en-tête de chapitre, pied de page,
    mention de copyright...). Les numéros de page ne sont pas comptés
    ici car ils changent à chaque page ; ils sont traités séparément
    par is_probably_page_number.
    """
    if len(doc_pages) < MIN_PAGES_FOR_HEADER_DETECTION:
        return set()

    counter = Counter()

    for page in doc_pages:
        lines = [l for l in page["text"].split("\n") if l.strip()]
        candidates = lines[:EDGE_LINES] + lines[-EDGE_LINES:]

        seen_on_this_page = set()

        for line in candidates:
            if is_probably_page_number(line):
                continue

            norm = normalize_line_for_matching(line)

            if norm and norm not in seen_on_this_page:
                counter[norm] += 1
                seen_on_this_page.add(norm)

    threshold = max(3, int(len(doc_pages) * MIN_HEADER_FOOTER_RATIO))

    return {norm for norm, count in counter.items() if count >= threshold}


def clean_page_lines(text, headers_footers_norm):
    """
    Supprime, uniquement en bordure du texte de la page, les lignes
    vides, les numéros de page isolés et les motifs d'en-tête/pied de
    page détectés. On ne touche jamais au milieu du texte : un motif
    qui apparaîtrait par coïncidence en plein milieu d'un paragraphe
    n'est donc jamais supprimé.
    """
    lines = text.split("\n")

    def should_remove(line):
        if not line.strip():
            return True
        if is_probably_page_number(line):
            return True
        return normalize_line_for_matching(line) in headers_footers_norm

    start = 0
    while start < len(lines) and should_remove(lines[start]):
        start += 1

    end = len(lines)
    while end > start and should_remove(lines[end - 1]):
        end -= 1

    return normalize_whitespace("\n".join(lines[start:end]))


def split_into_sections(doc_pages, headers_footers_norm):
    """
    Reconstitue le contenu d'un document page après page et le
    regroupe par section (un titre détecté ouvre une nouvelle section),
    plutôt que de couper arbitrairement à chaque changement de page
    comme le faisait la version précédente.
    """
    sections = []

    current_title = None
    current_lines = []
    current_page_start = None
    current_page_end = None

    def flush():
        text = "\n".join(current_lines).strip()
        if text:
            sections.append(
                {
                    "title": current_title,
                    "page_start": current_page_start,
                    "page_end": current_page_end,
                    "text": text,
                }
            )

    for page in doc_pages:
        cleaned = clean_page_lines(page["text"], headers_footers_norm)

        if not cleaned:
            continue

        for line in cleaned.split("\n"):

            if is_probable_heading(line):
                flush()
                current_title = line.strip()
                current_page_start = page["page"]
                current_page_end = page["page"]
                current_lines = [line.strip()]
            else:
                if current_page_start is None:
                    current_page_start = page["page"]
                current_page_end = page["page"]
                current_lines.append(line)

    flush()

    return sections


def split_section_text(text):
    """
    Découpe une section trop volumineuse en sous-chunks.
    Les coupures privilégient les paragraphes, puis les phrases,
    puis les espaces. Aucun chunk ne doit être inférieur à 100 caractères.
    """

    MIN_CHUNK_SIZE = 100

    text = text.strip()

    if not text:
        return []

    if len(text) <= CHUNK_SIZE:
        return [text]

    chunks = []
    start = 0

    while start < len(text):

        end = min(start + CHUNK_SIZE, len(text))

        # Dernier morceau
        if end == len(text):
            chunk = text[start:end].strip()

            if chunk:
                if len(chunk) < MIN_CHUNK_SIZE and chunks:
                    chunks[-1] = f"{chunks[-1]} {chunk}".strip()
                else:
                    chunks.append(chunk)

            break

        # Recherche d'une frontière naturelle
        boundary = text.rfind("\n\n", start + MIN_CHUNK_SIZE, end)

        if boundary == -1:
            boundary = text.rfind(". ", start + MIN_CHUNK_SIZE, end)

        if boundary == -1:
            boundary = text.rfind(" ", start + MIN_CHUNK_SIZE, end)

        if boundary == -1:
            boundary = end

        chunk = text[start:boundary].strip()

        if chunk:
            chunks.append(chunk)

        # Nouveau départ avec overlap
        next_start = boundary - OVERLAP

        # On ne repart jamais avant le début du chunk
        next_start = max(next_start, start + MIN_CHUNK_SIZE)

        # On avance jusqu'au prochain espace pour éviter
        # de commencer au milieu d'un mot
        while next_start < len(text) and not text[next_start].isspace():
            next_start += 1

        start = next_start

    return chunks


def create_chunks():

    if not INPUT_FILE.exists():
        print(f"Fichier introuvable : {INPUT_FILE}")
        return

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        pages = json.load(f)

    pages_by_doc = {}
    for page in pages:
        pages_by_doc.setdefault(page["document"], []).append(page)

    all_chunks = []
    chunk_id = 0
    total_sections = 0

    for document, doc_pages in pages_by_doc.items():

        doc_pages.sort(key=lambda p: p["page"])

        print(f"\nTraitement de : {document} ({len(doc_pages)} pages)")

        headers_footers = detect_running_headers_footers(doc_pages)

        if headers_footers:
            sample = list(headers_footers)[:3]
            print(f"  -> {len(headers_footers)} motif(s) d'en-tete/pied de page supprime(s), ex. : {sample}")
        else:
            print("  -> aucun en-tete/pied de page repetitif detecte")

        sections = split_into_sections(doc_pages, headers_footers)
        total_sections += len(sections)

        titled = sum(1 for s in sections if s["title"])
        print(f"  -> {len(sections)} section(s) detectee(s), dont {titled} avec titre identifie")

        for section in sections:

            sub_chunks = split_section_text(section["text"])

            for chunk_index, chunk_text in enumerate(sub_chunks):

                if chunk_index > 0 and section["title"]:
                    chunk_text = f"[{section['title']}]\n\n{chunk_text}"

                chunk_id += 1

                all_chunks.append(
                    {
                        "chunk_id": chunk_id,
                        "document": document,
                        "section": section["title"],
                        "page": section["page_start"],
                        "page_start": section["page_start"],
                        "page_end": section["page_end"],
                        "chunk_index": chunk_index,
                        "text": chunk_text,
                    }
                )

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(
            all_chunks,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print("\nCréation des chunks terminée.")
    print(f"Documents traités : {len(pages_by_doc)}")
    print(f"Pages analysées : {len(pages)}")
    print(f"Sections détectées : {total_sections}")
    print(f"Chunks créés : {len(all_chunks)}")
    print(f"Fichier : {OUTPUT_FILE}")


if __name__ == "__main__":
    create_chunks()