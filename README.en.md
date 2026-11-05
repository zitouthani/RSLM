# RSLM — Reproducible Small Language Model

Local document assistant based on retrieval-augmented generation (RAG). RSLM
combines FastAPI, Streamlit, Qdrant, Sentence Transformers, and Ollama. It
provides a reproducible application workflow; it does not train its own
language-model weights.

**Read this project in another language:** [Français](README.md) ·
[English](README.en.md) · [21 more languages](docs/readme/README.md)

The translated overviews are concise; full guides and reference commands are
maintained in French and English.

**Project website:** a bilingual French/English GitHub Pages site is provided
in [`site/`](site/). After enabling the GitHub Pages workflow, it will be
available at `https://<owner>.github.io/<repository>/`. In GitHub, select
**Settings → Pages → Build and deployment → GitHub Actions**.

See [`instructions.md`](instructions.md) and
[`securite.instructions.md`](securite.instructions.md) for contribution and
security guidance.

**Reproduce the project step by step:** read the
[reproduction guide](docs/reproduction-guide.en.md) and the
[realistic implementation stages](docs/project-stages.en.md).

## Features

- Search authorized PDFs and cite document pages.
- Local conversation history and user feedback.
- Admin upload, reindexing, deletion, backup, and restore of documents.
- Trace retrieval candidates, model context, and displayed citations.
- Configurable evaluation datasets for retrieval and answer checks.

## Architecture

```text
Browser → Streamlit → FastAPI → Ollama
                      └→ Qdrant
PDF → extraction and chunking → embeddings → Qdrant vector index
```

Local mode stores the Qdrant index under `data/qdrant`. Docker Compose uses a
named Docker volume. The two indexes are separate.

## Languages and technologies

- **Python**: API, Streamlit interface, indexing, and evaluation.
- **HTML, CSS, and JavaScript**: bilingual static website.
- **YAML**: Docker Compose and GitHub Actions workflows.
- **Markdown**: documentation and README overviews in 23 languages.
- **Dockerfile**: API image build.

Application logic is primarily written in Python. Models and their weights
are third-party dependencies and are not included in this repository.

## Requirements

- Python 3.11 or newer and the dependencies in `requirements.txt`.
- Ollama installed and running, with a chat model available, for example
  `qwen2.5:1.5b`.
- Docker Desktop on Windows/macOS or Docker Engine with the Compose plugin on
  Linux for the containerized API.
- On first use, the embedding and reranking models are downloaded from
  Hugging Face.

## Choose an installation path

- **Local** — run Streamlit, FastAPI, Qdrant, and Ollama on your machine.
- **Docker Compose** — run the API and Qdrant in containers, with Ollama on
  the host.

The step-by-step guides include PowerShell and Linux/macOS commands.
Multi-platform support is not yet covered by a CI matrix.

## Local installation

From PowerShell in the project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
ollama pull qwen2.5:1.5b
```

On Linux/macOS with Bash or zsh:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
ollama pull qwen2.5:1.5b
```

Set local values in `.env`. Generate a long random `RSLM_ADMIN_KEY` to
enable corpus administration, and use the same key in the API and Streamlit
sidebar. Keep local services bound to `127.0.0.1`.
`RSLM_ALLOWED_ORIGINS` controls browser origins allowed to call the API; it
defaults to `http://localhost:5173`. Do not add a public website to expose a
local corpus: CORS does not authenticate requests.

Start the API and UI in separate terminals:

```powershell
.\.venv\Scripts\python.exe -m uvicorn src.api_stream3:app --host 127.0.0.1 --port 8080
```

```powershell
$env:RSLM_API_URL = "http://127.0.0.1:8080"
.\.venv\Scripts\python.exe -m streamlit run src\app_stream.py
```

Open `http://localhost:8501`.

On Linux/macOS, with the virtual environment activated, start the API and
Streamlit in separate terminals:

```sh
python -m uvicorn src.api_stream3:app --host 127.0.0.1 --port 8080
```

```sh
RSLM_API_URL=http://127.0.0.1:8080 python -m streamlit run src/app_stream.py
```

## Document corpus

The repository does **not** include PDFs, downloaded model weights, embeddings,
or a document corpus. Only index and redistribute documents you are authorized
to process and share. Corpus files and derived indexes stay local and are
excluded from Git and Docker images.

You can add documents in either of these ways:

1. Configure `RSLM_ADMIN_KEY`, start the API, and upload PDFs from the
   Streamlit sidebar.
2. Place authorized PDFs in `documents` and prepare a local index:

   ```powershell
   python -m src.prepare_documents
   python -m src.create_chunks
   python -m src.create_embeddings
   python -m src.create_vector_db
   ```

Without an initial corpus, the API starts with an empty Qdrant collection and
does not generate document-grounded answers without sources.

## Docker Compose

Configure `.env`, start Ollama on the host, and pull the chat model, then run:

```powershell
docker compose up --build
```

Compose starts the API and Qdrant. Published ports are bound to `127.0.0.1`;
from a container, Ollama must be reachable at `host.docker.internal:11434`.
To run Streamlit on the host, install the Python dependencies and set
`RSLM_API_URL=http://127.0.0.1:8080`.

Docker does not copy local PDFs, model weights, or embeddings. A locally
created Qdrant index is separate from the Compose volume.

## Configuration and privacy

Use `.env.example` as the configuration reference. Never publish `.env`,
admin keys, logs, backups, conversations, or private documents.

`XAI_TRACE_ENABLED` defaults to `false` in `.env.example`. Traces written to
`logs/xai_trace.jsonl` may contain questions, conversation history, retrieved
document excerpts, and generated answers. Enable tracing only when needed.

Audit logging (`AUDIT_LOG_ENABLED`) and diagnostic logging that can include
questions, search queries, and retrieved excerpts
(`RSLM_DEBUG_CONTENT_LOGS`) are also disabled by default. Enable them only
for necessary local debugging, then protect and remove any resulting logs.

The admin key protects corpus administration only. It does not by itself make
the application safe for public access. The chat API is not a production-ready
public service; do not expose it to untrusted networks without authentication,
HTTPS, access controls, and resource limits.

## Tests and evaluation

Run the unit tests:

```powershell
python -m unittest discover -s tests -v
```

Retrieval and answer evaluation scripts expect `data/retrieval_eval.json` and
`data/answer_eval.json`, which are not included. Create annotations for your
own authorized corpus. Reports are written to the Git-ignored `logs` folder.

Lexical coverage and citation-presence metrics are regression aids, not proof
of truth or citation fidelity. See [xai.md](xai.md) for provenance and
evaluation limitations.

## License

Project source code is released under the MIT License; see [LICENSE](LICENSE).
This license does not apply to user-provided documents or third-party models,
weights, and their respective licenses.
