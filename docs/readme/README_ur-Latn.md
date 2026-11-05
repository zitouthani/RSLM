# RSLM

RSLM aik local, open-source document assistant hai jo retrieval-augmented generation (RAG) istemal karta hai. Is mein Streamlit, FastAPI, Qdrant, Sentence Transformers aur Ollama shamil hain.

**Doosri zabanain:** [Zabanon ki fehrist](README.md) · [Mukammal French documentation](../../README.md) · [Mukammal English documentation](../../README.en.md)

## Khususiyaat

- Sirf ijazat-shuda PDF mein talash aur document aur safhe ke hawale.
- Local document collection, guftagu ki history aur backups ka intizam.
- Talash ke nataij, model ko bheja gaya context aur jawab ke sources dekhna.
- Apne datasets se retrieval aur jawabat ki jaanch.

## Shuruat

Python 3.11 ya naya version aur local Ollama darkar hai. Docker Compose bhi ikhtiyari hai. Tafseeli qadam ke liye [French installation guide](../guide-reproduction.md) ya [English installation guide](../reproduction-guide.en.md) dekhein.

RSLM local application hai, hosted public service nahin. Repository mein PDFs, model weights ya indexes shamil nahin. Sirf woh documents process karein jinhein istemal karne ki ijazat ho; `.env` secrets ya private data commit na karein.

Source code MIT license ke tehat hai; user documents aur third-party models is mein shamil nahin. Is mukhtasar tarjume ko kisi native speaker ne alag se review nahin kiya.
