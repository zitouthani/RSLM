# Instructions for AI coding assistants

Follow the contribution guidance in [`../instructions.md`](../instructions.md)
and the security requirements in
[`../securite.instructions.md`](../securite.instructions.md).

Do not inspect, print, copy, stage, or modify local secrets or personal
corpus files unless the user explicitly requests a task involving those
specific files. Never stage or publish files on the user's behalf without an
explicit request. Preserve existing staged and unstaged changes.

For architecture and local setup, see [README.md](../README.md) and the
[reproduction guide](../docs/guide-reproduction.md). Keep API behavior in
`src/api_stream3.py` and the experimental React client in `frontend/`.

When changing answer generation, test both `/chat` and `/chat/stream`,
including streamed tokens and the final event: React displays tokens before
the final answer. Use synthetic inputs unless specific private files are
explicitly authorized. Prompt assertions or lexical checks alone do not prove
answer fidelity; see [XAI and evaluation](../xai.md).
