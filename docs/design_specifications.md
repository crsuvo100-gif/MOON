# MOON Cognitive Memory – Design Specifications

This document captures the **design** for the new components required to fulfill the Ultimate Cognitive Memory Infrastructure (gates 1‑14). It builds on the discovery report (`docs/memory_architecture.md`) and specifies the interfaces, data flows, and constraints for each subsystem.

---

## 1. Overall Architecture (recap)

```
USER → MOON TERMINAL/UI → MAIN BRAIN → MEMORY ORCHESTRATOR
               │                     │
               ▼                     ▼
   Working Memory (transient)   LocalMemoryStore (SQLite per‑type)
               │                     │
               ├─► VectorStore (FAISS) ──► CloudMemoryStore (PostgreSQL/Neon)
               │                     │
               ├─► SyncEngine (push/pull, conflict resolution)
               │                     │
               ├─► ContextEngine (ranking, token‑budget compression)
               │                     │
               ├─► MemoryPolicyEngine (read/write/share enforcement)
               │                     │
               └─► HealthService (FastAPI `/memory/health`)
```

*All components are **plug‑and‑play**: the `MemoryManager` (see `app/brain/memory_manager.py`) orchestrates them via dependency injection. New components expose a minimal abstract interface so they can be swapped or disabled.

---

## 2. Component Interfaces

### 2.1 `MemoryPolicyEngine`
* **Purpose** – Enforce *scope*, *ownership*, *agent‑level* and *trust* rules for any read/write/delete operation.
* **Key concepts**:
  - **Scope** (`Scope` enum from `app.memory.record`): determines visibility hierarchy (SYSTEM → GLOBAL → USER → PROJECT → AGENT → TEAM → TASK → SESSION).
  - **Owner IDs** – `owner_id`, `agent_id`, `project_id`, `task_id`, `session_id` stored on each `MemoryRecord`.
  - **Trusted flag** – If `trusted=True`, the record may be used to generate instructions; otherwise it is data‑only.
* **API**:
```python
class MemoryPolicyEngine:
    def __init__(self, requester: Requestor): ...
    def can_read(self, rec: MemoryRecord) -> bool: ...
    def can_write(self, rec: MemoryRecord) -> bool: ...
    def can_delete(self, rec: MemoryRecord) -> bool: ...
```
* **Requestor model** – minimal dataclass:
```python
@dataclass
class Requestor:
    user_id: str = ""
    agent_id: str = ""
    scope: Scope = Scope.GLOBAL
    is_trusted: bool = False
```
* **Decision logic** (high‑level):
  1. If the record’s `scope` is *equal* or *above* the requester’s scope → permit.
  2. If `owner_id` matches `requester.user_id` → permit.
  3. If `agent_id` matches and the request is from an agent → permit.
  4. For `trusted` records, the requester must also be `is_trusted` to execute them as instructions.
  5. Global/system records are readable by all, but writable only by privileged scopes (SYSTEM, GLOBAL).

### 2.2 `CloudMemoryStore`
* Implements abstract `MemoryStore` using asyncpg (PostgreSQL).
* Supports the same schema as `LocalMemoryStore` (JSONB columns for tags & provenance).
* Provides `async upsert/get/delete/query` compatible with existing `MemoryManager`.
* Handles `sync_status` updates and bulk push/pull.

### 2.3 `VectorStore`
* Wrapper around FAISS index stored under `~/.moon/memory/vectors/faiss.index`.
* API:
```python
class VectorStore:
    async def add(record: MemoryRecord, embedding: list[float]) -> None
    async def search(query_embedding: list[float], top_k: int = 10) -> list[MemoryRecord]
    async def rebuild() -> None
```
* Embedding generation is delegated to the **EmbeddingProvider** (outside scope).

### 2.4 `SyncEngine`
* Background task (run via `asyncio.create_task`) that periodically:
  1. Pulls pending local changes (`sync_status == PENDING`).
  2. Sends batches to the remote store.
  3. Pulls remote changes newer than last sync timestamp.
  4. Detects conflicts using `memory_id` and `version` – resolves with **last‑write‑wins** unless `source_type` is `USER` or `SYSTEM` (those win).
* Emits a conflict log file `~/.moon/memory/sync_conflicts.log`.

### 2.5 `ContextEngine`
* Aggregates records across layers respecting importance, relevance, and confidence.
* Uses `tiktoken` to enforce a token budget (default 8000 tokens for the main brain prompt).
* Returns a list of dicts `{"role": "memory", "content": <text>}` ready for injection into the LLM prompt.

### 2.6 `HealthService`
* FastAPI router mounted at `/memory/health`.
* Returns JSON with health of each subsystem, schema version, DB sizes, pending sync count, and vector index status.

---

## 3. Configuration (environment variables)
| Variable | Description | Default |
|----------|-------------|---------|
| `MOON_MEMORY_PATH` | Base directory for SQLite files and vector index. | `~/.moon/memory` |
| `MOON_DATABASE_URL` | PostgreSQL connection string for the cloud store. | *none* (feature disabled) |
| `MOON_SYNC_INTERVAL` | Background sync period in seconds. | `60` |
| `MOON_VECTOR_DIM` | Dimensionality of the embedding vectors (must match model). | `768` |
| `MOON_TOKEN_BUDGET` | Max tokens for context compression. | `8000` |

---

## 4. Testing Strategy
* **Unit tests** for each component (policy, cloud store, vector store, sync, context).
* **Integration test** (`tests/test_memory_system.py`) that runs a full cycle: write record → upsert → sync → vector search → context → memory manager actions.
* CI will enforce 100 % coverage on new modules.
* All tests are runnable with `pytest -q`.

---

## 5. Migration Path (from existing MOON)
1. Deploy `MemoryPolicyEngine` and enable it in `MemoryManager` (default permissive mode for backward compatibility). Existing records retain their current scopes.
2. Deploy `LocalMemoryStore` unchanged – no migration needed.
3. When `MOON_DATABASE_URL` is set, `CloudMemoryStore` will be instantiated and initial sync will copy existing SQLite data to the remote DB (one‑off migration script, not part of the gated implementation).
4. Enable `VectorStore` after embeddings are generated (future feature). The code path is safe to call even if the index file does not exist – it will be created lazily.
5. Once all subsystems are green, deprecate the legacy `app.memory.cognitive` utilities.

---

*Generated by Hermes Agent after read‑only discovery and roadmap definition.*
