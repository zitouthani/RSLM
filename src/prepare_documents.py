from pathlib import Path
import json
from pypdf import PdfReader


PROJECT_DIR = Path(__file__).resolve().parent.parent
DOCUMENTS_DIR = PROJECT_DIR / "documents"
OUTPUT_DIR = PROJECT_DIR / "data"

OUTPUT_DIR.mkdir(exist_ok=True)


def extract_documents():
    all_pages = []

    pdf_files = sorted(DOCUMENTS_DIR.glob("*.pdf"))

    if not pdf_files:
        print("Aucun fichier PDF trouvé dans :", DOCUMENTS_DIR)
        return

    print(f"{len(pdf_files)} document(s) trouvé(s).\n")

    for pdf_path in pdf_files:
        print(f"Lecture : {pdf_path.name}")

        reader = PdfReader(pdf_path)

        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""

            text = text.strip()

            if not text:
                continue

            all_pages.append(
                {
                    "document": pdf_path.name,
                    "page": page_number,
                    "text": text,
                }
            )

        print(f"  → {len(reader.pages)} pages")

    output_file = OUTPUT_DIR / "pages.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(
            all_pages,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print("\nExtraction terminée.")
    print(f"Pages extraites : {len(all_pages)}")
    print(f"Fichier créé : {output_file}")


if __name__ == "__main__":
    extract_documents()