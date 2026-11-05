# RSLM

RSLM este un asistent local open-source pentru documente, bazat pe generare augmentată prin recuperare (RAG). Proiectul combină Streamlit, FastAPI, Qdrant, Sentence Transformers și Ollama.

**Alte limbi:** [Indexul limbilor](README.md) · [Documentația completă în franceză](../../README.md) · [Documentația completă în engleză](../../README.en.md)

## Funcționalități

- Căutare în PDF-uri pentru care aveți drept de utilizare, cu referințe la document și pagină.
- Gestionarea colecției locale de documente, a istoricului conversațiilor și a copiilor de siguranță.
- Inspectarea rezultatelor recuperate, a contextului trimis modelului și a surselor răspunsurilor.
- Evaluarea căutării și a răspunsurilor cu seturi de date proprii.

## Noțiuni introductive

Sunt necesare Python 3.11 sau o versiune mai nouă și Ollama rulat local. Docker Compose este, de asemenea, o opțiune. Pentru pașii detaliați, consultați [ghidul de instalare în franceză](../guide-reproduction.md) sau [în engleză](../reproduction-guide.en.md).

RSLM este o aplicație locală, nu un serviciu public găzduit. Depozitul nu include PDF-uri, ponderi ale modelelor sau indexuri. Procesați numai documente pe care aveți dreptul să le folosiți și nu publicați secrete din `.env` sau date private.

Codul sursă este oferit sub licența MIT; aceasta nu acoperă documentele utilizatorilor sau modelele terților. Această traducere succintă nu a fost verificată independent de un vorbitor nativ.
