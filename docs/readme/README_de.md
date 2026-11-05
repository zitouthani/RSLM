# RSLM

RSLM ist ein quelloffener, lokal ausgeführter Dokumentassistent mit Retrieval-Augmented Generation (RAG). Das Projekt kombiniert Streamlit, FastAPI, Qdrant, Sentence Transformers und Ollama.

**Weitere Sprachen:** [Sprachverzeichnis](README.md) · [Vollständige Dokumentation auf Französisch](../../README.md) · [Vollständige Dokumentation auf Englisch](../../README.en.md)

## Funktionen

- Suche in freigegebenen PDFs mit Quellenangaben zu Dokumenten und Seiten.
- Verwaltung des lokalen Dokumentbestands, des Gesprächsverlaufs und von Sicherungen.
- Einblick in Suchtreffer, den Modellkontext und die Quellen einer Antwort.
- Bewertung von Suche und Antworten mit eigenen Datensätzen.

## Schnellstart

Benötigt werden Python 3.11 oder neuer und lokal ausgeführtes Ollama. Docker Compose ist ebenfalls möglich. Die ausführlichen Schritte stehen in der [französischen Installationsanleitung](../guide-reproduction.md) und der [englischen Installationsanleitung](../reproduction-guide.en.md).

RSLM ist eine lokale Anwendung und kein öffentlich gehosteter Dienst. Das Repository enthält keine PDFs, Modellgewichte oder Indizes. Verarbeiten Sie nur Dokumente, für die Sie die nötigen Rechte haben, und committen Sie weder `.env`-Geheimnisse noch private Daten.

Der Quellcode steht unter der MIT-Lizenz; Nutzerdokumente und Modelle Dritter sind davon ausgenommen. Diese Kurzfassung wurde nicht unabhängig von einer muttersprachlichen Person geprüft.
