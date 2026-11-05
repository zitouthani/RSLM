# RSLM

RSLM to lokalny asystent dokumentów typu open source, wykorzystujący generowanie wspomagane wyszukiwaniem (RAG). Łączy Streamlit, FastAPI, Qdrant, Sentence Transformers i Ollama.

**Inne języki:** [Indeks języków](README.md) · [Pełna dokumentacja po francusku](../../README.md) · [Pełna dokumentacja po angielsku](../../README.en.md)

## Funkcje

- Wyszukiwanie w PDF-ach, których możesz używać, z odnośnikami do dokumentów i stron.
- Zarządzanie lokalnym zbiorem dokumentów, historią rozmów i kopiami zapasowymi.
- Wgląd w wyniki wyszukiwania, kontekst modelu i źródła odpowiedzi.
- Ocena wyszukiwania i odpowiedzi na własnych zestawach danych.

## Pierwsze kroki

Wymagany jest Python 3.11 lub nowszy oraz lokalnie uruchomiona aplikacja Ollama. Możesz też wybrać Docker Compose. Szczegóły znajdziesz w [francuskim przewodniku instalacji](../guide-reproduction.md) lub [angielskim przewodniku](../reproduction-guide.en.md).

RSLM działa lokalnie i nie jest publicznie hostowaną usługą. Repozytorium nie zawiera plików PDF, wag modeli ani indeksów. Przetwarzaj tylko dokumenty, do których używania masz uprawnienia; nie commituj sekretów z `.env` ani prywatnych danych.

Kod źródłowy jest udostępniany na licencji MIT; nie obejmuje ona dokumentów użytkowników ani modeli stron trzecich. To krótkie tłumaczenie nie zostało niezależnie sprawdzone przez native speakera.
