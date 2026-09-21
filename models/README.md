# MOON — Physical Model Inventory (GGUF / Ollama weights)

MOON runs every agent on a **physically-installed local model** — no runtime
network pull is required once installed. This document records the model
inventory so the operational state is auditable and reproducible.

## Where the weights live

Ollama stores the actual GGUF weights as blobs under its models directory
(default `~/.ollama/models/blobs`, or the path in `OLLAMA_MODELS`). On the
reference host they are at:

```
/usr/share/ollama/.ollama/models/blobs/sha256-<digest>   (499 MB – 4.9 GB each)
```

Ollama serves these **offline** (`--offline`); MOON does not depend on any
remote model API for its local agents.

## Per-agent model binding (CPU-feasible set)

Every agent is bound (see `app/brain/agent_model_manager.py`) to a small model
that fits a CPU-only host. The distinct set every agent needs:

| Model | Size | Used by agents | Status |
|-------|------|----------------|--------|
| `qwen3:0.6b` | ~522 MB | default + base brain | PHYSICALLY PRESENT |
| `qwen2.5:1.5b` | ~986 MB | router, summarizer, memory, writing, design, audio, voice | PHYSICALLY PRESENT |
| `qwen2.5:3b` | ~1.9 GB | planning, coordinator, research, security, cyber, legal, medical, finance, translation, infra, review, critic, manager, science | PHYSICALLY PRESENT |
| `qwen2.5-coder:1.5b` | ~986 MB | coding, debug, toolsmith, github_sync, qa | PHYSICALLY PRESENT |
| `deepseek-r1:1.5b` | ~1.1 GB | math, science (reasoning) | PHYSICALLY PRESENT |

All five were verified to **generate text offline** via the OpenAI-compatible
endpoint (`http://127.0.0.1:11434/v1/chat/completions`).

## GPU-only models (NOT pulled on CPU hosts)

`RECOMMENDED_FOR_CAPABLE_HW` in `agent_model_manager.py` lists stronger models
(`qwen2.5-coder:7b`, `qwen3:8b`, `deepseek-r1:8b`, `llava:7b`, etc.). These are
optional and only used when MOON runs on a GPU host (set via `.env` /
`STRONG_MODEL_NAME`). They are intentionally not pulled on CPU-only machines.

## Installing the models on a fresh machine

From a fresh `git clone`, run the Python installer which pulls every required
local model best-effort:

```bash
python -m moon install        # creates venv, deps, and pulls REQUIRED_MODELS
# or directly:
python install_moon.py        # pulls qwen3:0.6b, qwen2.5:3b, qwen2.5:1.5b,
                              #          qwen2.5-coder:1.5b, deepseek-r1:1.5b
```

`ollama` must be installed and running first (see README). Each pull downloads
the real GGUF weights into Ollama's blob store.

## Verifying models are physically present

```bash
ollama list                   # shows installed models + sizes
python -m moon doctor        # reports "Model runtime (Ollama): reachable"
# Or a direct offline completion test:
curl http://127.0.0.1:11434/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"model":"qwen2.5:3b","messages":[{"role":"user","content":"say: LOCAL-OK"}],"stream":false}'
```
