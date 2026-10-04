# MOON Cognitive Memory Infrastructure

## Architecture

```
                      USER
                        |
                        v
                MOON TERMINAL/UI
                        |
                        v
                 MAIN BRAIN
                        |
                        v
               MEMORY ORCHESTRATOR
                        |
    +------------------+------------------+
    |                  |                  |
    v                  v                  v
WORKING MEMORY      MEMORY RETRIEVAL   MEMORY WRITER
    |                  |                  |
    |          +-------+--------+         |
    |          |                |         |
    v          v                v         v
Current Task   LOCAL          GLOBAL    Candidate
Memory         Memory     Memories
    |              |
    v              v
  SQLite        PostgreSQL
    |              |
    v              v
Vector DB      Cloud Vector
    |              |
    +------+-------+
           |
    SYNC ENGINE
           |
    CONFLICT ENGINE
           |
    CONSOLIDATION
           |
    LONG-TERM MEMORY
```

## Memory Layers

| Layer | Name | Description |
|-------|------|-------------|
| 1 | Working Memory | Current task, active subtasks, recent tool results |
| 2 | Short-Term Memory | Recent conversation/task info with configurable retention |
| 3 | Episodic Memory | Events with time, task, agents, result, evidence |
| 4 | Semantic Memory | Stable facts and knowledge |
| 5 | Procedural Memory | How things are done (documented vs inferred) |
| 6 | User Memory | Persistent user-approved information |
| 7 | Project Memory | Project structure, architecture, dependencies |
| 8 | Agent Memory | Private memory per agent |
| 9 | Shared Memory | Explicitly shared across agents |

## Memory Scopes

Every memory has a scope: SYSTEM, GLOBAL, USER, PROJECT, AGENT, TEAM, TASK, SESSION.

Agent private memory (scope=AGENT) is isolated — other agents cannot access it without authorization.

## Configuration

All settings are in `app/config/settings.py` (pydantic BaseSettings). Override via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `MOON_MEMORY_PATH` | `~/.moon/memory` | Local memory data directory |
| `MOON_DATABASE_URL` | (empty) | Cloud PostgreSQL URL. Empty = local-only |
| `MOON_SYNC_ENABLED` | `true` | Enable cloud synchronization |
| `MOON_SYNC_INTERVAL` | `300` | Seconds between sync attempts |
| `MOON_MEMORY_LIMIT` | `100000` | Max local records before archival |
| `MOON_CONTEXT_MEMORY_BUDGET` | `2048` | Token budget for memory in context |
| `MOON_BACKUP_PATH` | `~/.moon/memory/backups` | Backup storage directory |
| `MOON_MEMORY_CACHE_ENABLED` | `true` | Enable retrieval cache |
| `MOON_MEMORY_CACHE_TTL` | `60` | Cache TTL in seconds |
| `MOON_MEMORY_OFFLINE_MODE` | `false` | Force offline mode |

## Local-First Operation

MOON operates local-first:
- Primary storage: SQLite at `~/.moon/memory/moon.db`
- Vector storage: local vector index
- Cloud sync: queued, non-blocking
- Offline: full functionality, sync queue persists

## Memory API

The memory API is mounted at `/api/memory/` in the terminal interface.

Endpoints:
- `POST /api/memory/store` — Store a memory
- `GET /api/memory/search` — Search memories
- `GET /api/memory/{id}` — Get a memory
- `PUT /api/memory/{id}` — Update a memory
- `DELETE /api/memory/{id}` — Delete a memory
- `POST /api/memory/forget` — Forget memories matching query
- `GET /api/memory/health` — Memory health status
- `POST /api/memory/backup` — Create backup
- `POST /api/memory/restore` — Restore from backup
- `POST /api/memory/export` — Export memories
- `POST /api/memory/import` — Import memories
- `POST /api/memory/sync` — Trigger sync

## Agent Memory Interface

Agents access memory through `BaseAgent` methods (spec 61):

```python
# Search memory
results = await agent.memory_search("Python project", top_k=5, scope="PROJECT")

# Store memory
memory_id = await agent.memory_store(
    "MOON uses Python 3.14",
    memory_type="semantic",
    importance=0.8,
    scope="PROJECT",
)

# Forget memories
deleted = await agent.memory_forget("old deployment config")

# Update memory
success = await agent.memory_update(memory_id, "MOON uses Python 3.14+")
```

Agents NEVER access database tables directly.

## Memory Events

The system emits events via the EventBus (spec 60):
- `memory.created`, `memory.updated`, `memory.deleted`
- `memory.retrieved`, `memory.promoted`, `memory.archived`
- `memory.consolidated`
- `memory.sync_started`, `memory.sync_completed`, `memory.sync_failed`
- `memory.conflict`
- `memory.backup_created`, `memory.restore_completed`

## Security

- Secret detection (13 patterns) before persistence
- Secrets are NEVER stored as normal memory
- Memory content is treated as DATA, not instructions
- Retrieved memory cannot override system instructions
- External/untrusted content stored as UNTRUSTED_DATA

## Testing

```bash
# Run all memory tests
python -m pytest tests/test_cognitive_memory.py tests/test_cognitive_memory_full.py -v

# Run full test suite
python -m pytest tests/ -v
```

## File Structure

```
app/memory/
├── __init__.py
├── cognitive.py          # Core cognitive memory (CognitiveMemory)
├── context_engine.py    # Context engine (ContextEngine)
├── sync.py              # Sync engine (SyncEngine)
├── record.py            # Memory record model (MemoryRecord)
├── store.py             # Memory store (MemoryStore)
├── candidate.py         # Candidate pipeline
├── semantic_search.py   # Semantic search
├── vector_db.py         # Vector database
├── vector_store.py      # Pluggable vector store
├── security.py          # Secret detection + sanitize
├── retrieval.py         # HybridRetriever + RetrievalCache
├── commands.py          # NL command parser
├── health.py            # MemoryHealthService
├── backup.py            # Backup/restore/export/import
├── api.py               # FastAPI router
├── memory_maintenance.py # MemoryMaintenance
├── memory_cache.py      # MemoryCache
├── working_memory.py    # Working memory
├── short_term.py        # Short-term memory
├── long_term.py         # Long-term memory
├── episodic_memory.py   # Episodic memory
└── advanced/
    ├── orchestrator.py      # AdvancedMemoryOrchestrator
    ├── unified_search.py    # Unified search
    ├── proactive_memory.py  # Proactive memory
    ├── compaction.py        # Compaction
    ├── consolidation.py     # Consolidation
    └── analytics.py         # MemoryAnalytics
```
