import json

pages = json.load(open("data/pages.json", encoding="utf-8"))
doc_pages = [p for p in pages if p["document"] == "ouvrage_2.pdf"]

for i in [10, len(doc_pages)//2, len(doc_pages)-10]:
    page = doc_pages[i]
    lines = [l for l in page["text"].split("\n") if l.strip()]
    print(f"\n=== Page {page['page']} — 5 premières lignes ===")
    for l in lines[:5]:
        print(repr(l))
    print(f"=== Page {page['page']} — 3 dernières lignes ===")
    for l in lines[-3:]:
        print(repr(l))