# RSLM

RSLM es un asistente documental local y de código abierto que utiliza generación aumentada por recuperación (RAG). Combina Streamlit, FastAPI, Qdrant, Sentence Transformers y Ollama.

**Otros idiomas:** [Índice de idiomas](README.md) · [Documentación completa en francés](../../README.md) · [Documentación completa en inglés](../../README.en.md)

## Funciones

- Busca en PDF autorizados y cita documentos y páginas.
- Gestiona una colección documental local, el historial de conversaciones y copias de seguridad.
- Permite inspeccionar los resultados recuperados, el contexto enviado al modelo y las fuentes de las respuestas.
- Evalúa la recuperación y las respuestas con conjuntos de datos propios.

## Primeros pasos

Necesitas Python 3.11 o posterior y Ollama ejecutándose localmente. También puedes usar Docker Compose. Consulta la [guía de instalación en francés](../guide-reproduction.md) o la [guía en inglés](../reproduction-guide.en.md) para ver todos los pasos.

RSLM es una aplicación local, no un servicio público alojado. El repositorio no incluye PDF, pesos de modelos ni índices. Procesa solo documentos que tengas permiso para usar y no subas secretos de `.env` ni datos privados.

El código fuente usa la licencia MIT; esta no cubre los documentos de usuario ni los modelos de terceros. Esta traducción resumida no ha sido revisada de forma independiente por una persona nativa.
