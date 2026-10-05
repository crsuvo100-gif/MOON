# MOON Cognitive Memory Architecture

```
+-------------------+      +-------------------+      +-------------------+
|    Main Brain     | ---> | CognitiveMemory   | ---> | LocalMemoryStore |
| (Orchestrator)   |      | Manager (Facade)  |      | (SQLite)          |
+-------------------+      +-------------------+      +-------------------+
        |                         |                         |
        |                         |                         |
        |                         |                         |
        v                         v                         v
+-------------------+   +-------------------+   +-------------------+
|   Context Engine  |   |  HybridRetriever  |   |  Vector Store (FAISS) |
| (budget, rank,    |   | (semantic + kw)   |   | (optional, lazy)   |
|  compress)        |   +-------------------+   +-------------------+
+-------------------+            ^                     ^
        ^                        |                     |
        |                        |                     |
        |                +-------------------+          |
        |                |  Sync Engine      |----------+ 
        |                | (queue, retry,   |
        |                |  conflict resolve)|
        |                +-------------------+
        |                         |
        |            +-------------------+
        +----------> | CloudMemoryStore |
                     | (Postgres/Neon) |
                     +-------------------+
```

## Components

1. **Main Brain (Orchestrator)** – decides tasks, queries memory via the `CognitiveMemoryManager`, builds context, and routes to agents.
2. **CognitiveMemoryManager** – the public façade used by agents (`search`, `store`, `update`, `forget`). Handles candidate pipeline, policy checks, deduplication, importance/confidence defaults, and emits memory events.
3. **LocalMemoryStore** – SQLite‑based storage under `~/.moon/memory/moon.db`. Provides CRUD, versioning, soft‑delete, and health diagnostics.
4. **Vector Store (FAISS)** – optional lightweight vector index for semantic search. Populated on demand from records whose embeddings are ready.
5. **HybridRetriever** – combines keyword search (SQLite) with semantic similarity (FAISS) and applies scoring based on importance, confidence, recency, scope, etc.
6. **Sync Engine** – background queue that pushes pending changes to a `CloudMemoryStore` (e.g., Neon PostgreSQL). Handles idempotent retries, conflict detection, and updates `sync_status`.
7. **CloudMemoryStore** – abstract interface for a remote PostgreSQL‑compatible store. Not implemented yet; a stub exists for future integration.
8. **Context Engine** – collects relevant memories, rewrites queries, ranks results, compresses to fit the model token budget, and returns the final context payload to the Main Brain.
9. **MemoryPolicyEngine** – enforces read/write permissions per scope, agent, and user, and blocks secret storage.
10. **Event Bus** – publishes events (`memory.created`, `memory.retrieved`, `memory.updated`, …) for observability and UI integration.

The architecture respects the **local‑first** principle: all operations succeed offline; synchronization is best‑effort and does not block local workflows.
