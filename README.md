# Octron V4.0

**Offline, Soulbound Tactical AI** — powered by [Ollama](https://ollama.com/) + [Qdrant](https://qdrant.tech/) vector memory.

Octron is a local-first AI assistant with long-term memory, emotional calibration, and a custom personality engine. All data stays on your machine.

## Requirements

* **Python 3.10+**
* **Ollama** running locally with these models pulled:

  * `mistral-nemo` (chat model used by `octron_cli.py` / `octron_api.py`)
  * `mxbai-embed-large` (embedding model)
  * `dolphin-llama3` (default fallback model for the sleep-cycle consolidation; not required if you always pass `model_name` explicitly)
* **Qdrant** (embedded, no separate server needed)

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Pull the required Ollama models
ollama pull mistral-nemo
ollama pull mxbai-embed-large
ollama pull dolphin-llama3

# 3. Run Octron
python octron_cli.py
```

PDF ingestion needs a specific package, not just "any pdfminer": `pdfminer` (legacy, unmaintained) and `pdfminer.six` install to the same
top-level module name, so if you ever see PDF injection fail with
`No module named 'pdfminer.high_level'`, run:

```bash
pip uninstall pdfminer
pip install pdfminer.six
```

## Architecture

```
octron_cli.py            # Main chat interface (start here)
V4octron_memory.py       # Vector memory system (Qdrant + Ollama embeddings)
V4octron_reasoning.py    # Structured reasoning engine (doctrine + memory evidence)
octron_injector.py       # File ingestion — reads files from upload_here/
octron_soulbind.py       # PDF page-by-page ingestion
octron_sleep.py          # Memory consolidation on shutdown
emotion_core.py          # Emotional tone detection & response calibration
ctx_firewall.py          # Startup integrity checks (persisted hash comparison)
octron_diagnose.py       # Self-diagnosis — Octron inspects his own code
IDV2_core.txt            # Identity / personality definition
upload_here/             # Drop files here for injection

# Mobile / remote stack (optional, separate from the desktop CLI)
octron_api.py            # FastAPI backend — /chat endpoint, uses V4octron_reasoning
octron_mobile_ui.py      # Streamlit chat UI, talks to octron_api.py over HTTP
octron_devtool.py        # Streamlit dashboard: diagnose / dependency map / code editor
launch_octron.py         # Starts octron_api.py + octron_mobile_ui.py together
```

**Note:** `V4octron_reasoning.py` is a standalone reasoning/evidence module.
`octron_cli.py` (the desktop chat loop) does its own memory recall directly
via `V4octron_memory.recall_memory()` and does not call the reasoning engine —
only `octron_api.py` (the mobile backend) currently wires it in.

## CLI Commands

|Command|Description|
|-|-|
|`exit`|Shutdown + run sleep cycle to consolidate memories|
|`mem`|Show total memory fragment count|
|`stats`|Detailed memory breakdown by source and topic|
|`debug`|Toggle debug mode (shows memory recall + emotion data)|
|`deep`|Toggle deep search (hides identity files from recall)|
|`tokens` / `context`|Show real token usage from Ollama's last response vs. `NUM_CTX`, plus session totals|
|`new` / `refresh` / `reset`|Consolidate the current session into memory (same as `exit`'s sleep cycle), then clear the in-process conversation/context — no need to kill and restart the terminal|
|`diagnose`|Run self-diagnosis on all Octron modules|
|`code <module>`|View the source code of a specific module|
|`teach <topic>: <info>`|Teach Octron a new fact with topic tagging|

## Feeding Octron Knowledge

**Method 1 — Teach command (quick facts):**

```
Operator: teach cars: My car is a 2020 Honda Civic, black, manual transmission.
```

**Method 2 — File injection (bulk knowledge):**
Drop `.txt`, `.md`, `.pdf`, or `.py` files into `upload_here/`, then run:

```bash
python octron_injector.py
```

**Method 3 — PDF Soulbind (page-by-page):**

```bash
python octron_soulbind.py path/to/document.pdf
```

## Mobile / Remote Interface

```bash
python launch_octron.py
```

Starts the FastAPI backend (`octron_api.py`, port 8000) and the Streamlit
mobile UI (`octron_mobile_ui.py`, port 8501) together. Needs `fastapi`,
`uvicorn`, `pydantic`, `streamlit`, and `requests` — all included in
`requirements.txt`.

`octron_api.py`'s `/chat` endpoint is stateless — the client (the Streamlit
UI, or anything else you point at it) sends the full conversation history
with every request, so there's no server-side session to manage. Each
response includes a `tokens` object (`prompt`, `completion`, `total`,
`context_window`, `percent_used`) straight from Ollama's own counts. The
mobile UI shows this live in the header and pops a warning past 85% full;
its **New Session** button just clears the client-side history array —
Octron's stored memory (`qdrant_data/`) is untouched either way.

## Key Improvements in V4

* **Consistent module naming**: memory and reasoning engines are named
  `V4octron_memory.py` / `V4octron_reasoning.py` so `octron_diagnose.py` and
  every importer agree on the same files (previously `octron_diagnose.py`
  pointed at a nonexistent `V2octron_memory.py` and always reported it MISSING).
* **One reasoning engine, not two**: the older, unfiltered reasoning module
  is gone. `octron_api.py` now uses the same relevance-aware evidence logic
  as the rest of the project, and reuses the memory module's single shared
  Qdrant client instead of opening a second connection per request.
* **Real tamper detection**: `ctx_firewall.py` persists file hashes to
  `.octron_integrity.json` on first run and actually compares against them
  on every run after — previously the hash table was hardcoded empty, so
  the "MODIFIED" check could never fire.
* **Accurate self-diagnosis**: `octron_diagnose.py` now checks for the
  correct PDF packages (`pdfminer.six` specifically, not just any module
  named `pdfminer`) plus the mobile-stack dependencies, instead of reporting
  a false "installed" status.
* **No more hallucination**: uses `ollama.chat()` with proper role separation and stop tokens
* **Relevance scoring**: Memory results below a confidence threshold are filtered out
* **Content deduplication**: Same information won't be stored twice
* **Topic tagging**: Memories are tagged by topic for better retrieval
* **Source citation**: Octron tracks where each memory came from
* **Self-diagnosis**: Octron can inspect and explain his own code
* **Cleaner context**: Emotion prefixes are display-only, not saved to chat history
