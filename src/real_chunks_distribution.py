import json

chunks = json.load(open("data/chunks.json", encoding="utf-8"))
lengths = sorted(chunks, key=lambda c: len(c["text"]))

print(f"Chunk le plus court : {len(lengths[0]['text'])} caractères")
print(f"Chunk le plus long  : {len(lengths[-1]['text'])} caractères")
print(f"Médiane approximative : {len(lengths[len(lengths)//2]['text'])} caractères")

print("\n--- Les 5 chunks les plus courts ---")
for c in lengths[:5]:
    print(f"\n[{c['document']} p.{c['page']}] section = {c['section']!r}")
    print(c["text"])