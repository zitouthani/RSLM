# RSLM — Reproducible Small Language Model

Local document assistant based on retrieval-augmented generation (RAG). RSLM
combines FastAPI, Streamlit, an experimental React/Vite frontend, Qdrant,
Sentence Transformers, and Ollama. It
provides a reproducible application workflow; it does not train its own
language-model weights.

**Read this project in another language:** [Français](README.md) ·
[English](README.en.md) · [21 more languages](docs/readme/README.md)

The translated overviews are concise; full guides and reference commands are
maintained in French and English.

**Project website:** [visit the bilingual French/English site](https://zitouthani.github.io/RSLM/).
Its [source code](site/) and GitHub Pages deployment workflow are included in
this repository.

See [`instructions.md`](instructions.md) and
[`securite.instructions.md`](securite.instructions.md) for contribution and
security guidance.

**Reproduce the project step by step:** read the
[reproduction guide](docs/reproduction-guide.en.md) and the
[realistic implementation stages](docs/project-stages.en.md).

## Features

- Search authorized PDFs and cite document pages.
- Local conversation history and user feedback.
- Experimental React/Vite chat UI, separate from Streamlit administration.
- Admin upload, reindexing, deletion, backup, and restore of documents.
- Trace retrieval candidates, model context, and displayed citations.
- Inspect a per-answer retrieval graph in React and Streamlit, including candidate ranks and scores.
- Configurable evaluation datasets for retrieval and answer checks.

## Architecture

```text
Browser → Streamlit or React/Vite → FastAPI → Ollama
                                     └→ Qdrant
PDF → extraction and chunking → embeddings → Qdrant vector index
```

Local mode stores the Qdrant index under `data/qdrant`. Docker Compose uses a
named Docker volume. The two indexes are separate.

## Languages and technologies

- **Python**: API, Streamlit interface, indexing, and evaluation.
- **React, JavaScript, and Vite**: experimental chat UI in `frontend/`.
- **HTML, CSS, and JavaScript**: bilingual static website.
- **YAML**: Docker Compose and GitHub Actions workflows.
- **Markdown**: documentation and README overviews in 23 languages.
- **Dockerfile**: API image build.

Application logic is primarily written in Python. Models and their weights
are third-party dependencies and are not included in this repository.

## Requirements

- Python 3.11 or newer and the dependencies in `requirements.txt`.
- Node.js 20.19+ or 22.12+ and npm, only for the React/Vite frontend.
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

### Try the React/Vite interface

The comparison UI is independent and does not replace Streamlit. It covers
chat, sources, and feedback; corpus administration remains in Streamlit.
Keep the API running in one terminal, then use another:

```powershell
Set-Location frontend
npm install
Copy-Item .env.example .env.local
npm run dev
```

Open `http://localhost:5173`. On Linux/macOS, use `cp .env.example
.env.local` instead of `Copy-Item`. Set the API URL with
`VITE_API_BASE_URL` in `frontend/.env.local`. React conversation history is
stored in this browser’s `localStorage` and is not shared with Streamlit.
To index PDFs already in `documents/`, configure `RSLM_ADMIN_KEY` in `.env`
before starting the API. In React’s “Corpus documentaire” panel, enter the
key, load the list, and click **Indexer** for files that are not indexed yet.
Copying a PDF into the folder does not index it automatically; reindexing an
already indexed document first creates a backup.

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

Run the frontend tests and production build from `frontend/`:

```sh
npm install
npm test -- --run
npm run build
```

Retrieval and answer evaluation scripts expect `data/retrieval_eval.json` and
`data/answer_eval.json`, which are not included. Create annotations for your
own authorized corpus. Reports are written to the Git-ignored `logs` folder.

Lexical coverage and citation-presence metrics are regression aids, not proof
of truth or citation fidelity. See [xai.md](xai.md) for provenance and
evaluation limitations.

The retrieval graph shows permitted candidates, their ranking, and the
passages prepared for the model. It describes the retrieval process, not a
corpus knowledge graph. The displayed terms are used for the lexical guardrail;
the initial search is vector-based. Selected passages start at a question term
when needed and remain subject to context limits; sources and the graph display
the same text. Other candidates remain previews. These document excerpts are
stored with the conversation: in browser `localStorage` and JSON exports for
React, or in the local conversation history for Streamlit. Details
of excluded documents or rejected searches are not sent in the graph. Older
answers do not have a reconstructed graph.

## Hardware and performance

The machine used for local tests, inspected on November 8, 2026, has:

- Windows 11 Pro, an Intel Core i5-1135G7 (4 cores, 8 threads), and 15.7 GiB of usable RAM.
- Integrated Intel Iris Xe graphics, sharing system memory.
- A roughly 954 GiB KIOXIA NVMe SSD hosting the system and project volumes.
- CPU-only PyTorch 2.13.0 and Ollama 0.34.1. PyTorch detected neither CUDA nor a usable Intel XPU device in this environment.

Files on these volumes already use the SSD: it can improve loading and indexing, but does not guarantee faster generation. Ollama and PyTorch manage accelerators independently. `vulkaninfo --summary` detects Iris Xe with Vulkan 1.4 and Intel driver 101.6913. An isolated Ollama 0.34.1 instance detected this GPU when started with `OLLAMA_VULKAN=1` and `OLLAMA_IGPU_ENABLE=1`; without the latter, Ollama ignored it. No model was loaded onto the GPU during this test: generation and any speedup remain unverified, and the integrated GPU shares system RAM. Consult the [Ollama hardware documentation](https://docs.ollama.com/gpu) before making changes.

To inspect the project's Python environment and the placement of a loaded Ollama model:

```powershell
.\.venv\Scripts\python.exe -c "import torch; print(torch.__version__, torch.cuda.is_available(), hasattr(torch, 'xpu') and torch.xpu.is_available())"
ollama ps
```

On ten synthetic text pairs, the BGE reranker took 13.64 s with batches of 2 versus 22.33 to 24.58 s with batches of 8; the ranking was identical in that test. These figures measure neither a complete response nor quality on a real corpus. CPU/GPU comparisons and document-based performance remain unmeasured; results depend on available memory and passage length.

On an authorized local PDF, three reads and text extractions of the first five pages using `pypdf` took 0.64, 0.51, and 0.48 s, with a median of 0.51 s. The system cache was not cleared: this includes PDF processing and is neither an SSD throughput test nor a full indexing measurement.

## License

Project source code is released under the MIT License; see [LICENSE](LICENSE).
This license does not apply to user-provided documents or third-party models,
weights, and their respective licenses.
