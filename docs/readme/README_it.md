# RSLM

RSLM è un assistente documentale locale e open source che usa la generazione aumentata dal recupero (RAG). Combina Streamlit, FastAPI, Qdrant, Sentence Transformers e Ollama.

**Altre lingue:** [Indice delle lingue](README.md) · [Documentazione completa in francese](../../README.md) · [Documentazione completa in inglese](../../README.en.md)

## Funzionalità

- Ricerca nei PDF autorizzati con riferimenti a documenti e pagine.
- Gestione del corpus locale, della cronologia delle conversazioni e dei backup.
- Ispezione dei risultati recuperati, del contesto inviato al modello e delle fonti delle risposte.
- Valutazione del recupero e delle risposte con dataset personalizzati.

## Per iniziare

Servono Python 3.11 o versioni successive e Ollama in esecuzione locale. È possibile usare anche Docker Compose. Per i passaggi dettagliati, consulta la [guida all'installazione in francese](../guide-reproduction.md) o [in inglese](../reproduction-guide.en.md).

RSLM è un'applicazione locale, non un servizio pubblico ospitato. Il repository non include PDF, pesi dei modelli o indici. Elabora solo documenti che sei autorizzato a usare e non pubblicare segreti `.env` o dati privati.

Il codice sorgente è distribuito con licenza MIT; la licenza non copre i documenti degli utenti né i modelli di terze parti. Questa traduzione sintetica non è stata verificata in modo indipendente da una persona madrelingua.
