# MOON Cognitive Memory Infrastructure — Deployment Guide

## Executive Summary

MOON already contains a comprehensive cognitive memory infrastructure (7,742 lines across 33 modules in `app/memory/`). All 196 memory tests pass. The system is fully integrated into the orchestrator and terminal.

This document covers:
1. Free server deployment options for 24/7 uptime
2. Architecture overview
3. Configuration
4. Installation
5. Verification

---

## 1. Free Server Deployment Options

### Option A: Render (Recommended)

**Free Tier:** 750 instance hours/month (enough for one always-on service)

**Pros:**
- Git-based deployment (push to GitHub, auto-deploy)
- Free SSL
- Persistent storage available
- Easy environment variable management

**Cons:**
- Cold starts on free tier (30-60 seconds)
- 15-minute inactivity sleep

**Deployment Steps:**
1. Push code to GitHub
2. Create Render account → New Web Service
3. Connect GitHub repo
4. Build Command: `pip install -r requirements.txt`
5. Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
6. Set environment variables in Render dashboard

### Option B: Railway

**Free Tier:** $5/month credit (enough for one small service)

**Pros:**
- No cold starts
- Generous free credit
- Easy deployment

**Cons:**
- Usage-based billing
- Requires credit card for verification

### Option C: Oracle Cloud Free Tier

**Free Tier:** Always Free (2 AMD VMs, 4 ARM cores, 24GB RAM)

**Pros:**
- Truly free, no credit card
- No sleep/cold start
- Full root access

**Cons:**
- Complex setup
- Requires account verification
- ARM architecture may have compatibility issues

### Option D: Self-Hosted with Tunnel (Current Setup)

**Cost:** $0 (uses existing hardware)

**Pros:**
- Full control
- No external dependencies
- Already configured

**Cons:**
- Requires local machine to be online
- Dynamic IP issues

---

## 2. Architecture Overview

### Memory Layers Implemented

| Layer | Module | Status |
|-------|--------|--------|
| Working Memory | `app/memory/working_memory.py` | ✅ Complete |
| Short-Term Memory | `app/memory/short_term.py`, `enhanced_short_term.py` | ✅ Complete |
| Episodic Memory | `app/memory/episodic_memory.py` | ✅ Complete |
| Semantic Memory | `app/memory/semantic_search.py` | ✅ Complete |
| Procedural Memory | `app/memory/layers.py` | ✅ Complete |
| User Memory | `app/memory/record.py` (Scope.USER) | ✅ Complete |
| Project Memory | `app/memory/record.py` (Scope.PROJECT) | ✅ Complete |
| Agent Memory | `app/memory/record.py` (Scope.AGENT) | ✅ Complete |
| Shared Memory | `app/memory/record.py` (Scope.TEAM) | ✅ Complete |

### Core Components

| Component | Module | Lines |
|-----------|--------|-------|
| Memory Record Model | `app/memory/record.py` | 222 |
| Local Store (SQLite) | `app/memory/store.py` | 507 |
| Cloud Store (PostgreSQL) | `app/memory/cloud_store.py` | 537 |
| Sync Engine | `app/memory/sync.py` | 420 |
| Candidate Pipeline | `app/memory/candidate.py` | 298 |
| Hybrid Retriever | `app/memory/retrieval.py` | 261 |
| Context Engine | `app/memory/context_engine.py` | 282 |
| Cognitive Manager | `app/memory/cognitive.py` | 428 |
| Policy Engine | `app/memory/policy.py` | 188 |
| Security (Secret Detection) | `app/memory/security.py` | 114 |
| Health Service | `app/memory/health.py` | 171 |
| Backup/Restore | `app/memory/backup.py` | 205 |
| Vector Store | `app/memory/vector_store.py` | 148 |
| API Router | `app/memory/api.py` | 295 |
| Advanced Orchestrator | `app/memory/advanced/orchestrator.py` | 329 |
| Consolidation | `app/memory/advanced/consolidation.py` | 213 |
| Compaction | `app/memory/advanced/compaction.py` | 319 |
| Analytics | `app/memory/advanced/analytics.py` | 227 |

**Total: 7,742 lines across 33 modules**

---

## 3. Configuration

### Environment Variables

```bash
# Memory Storage
MOON_MEMORY_PATH=/home/meow/.moon/memory
MOON_MEMORY_BACKEND=local  # or 'cloud' for PostgreSQL

# Cloud Database (optional)
MOON_DATABASE_URL=postgres://user:pass@host:5432/moon_db

# Embeddings
EMBEDDING_BASE_URL=
EMBEDDING_MODEL=all-MiniLM-L6-v2
EMBEDDING_DIM=384

# Sync
MOON_SYNC_ENABLED=true
MOON_SYNC_INTERVAL=300

# Context
MOON_CONTEXT_MEMORY_BUDGET=0.35

# Backup
MOON_BACKUP_PATH=/home/meow/.moon/memory/backups
```

### Local-First Operation

MOON operates local-first by default:
- All writes go to SQLite immediately
- Cloud sync is queued and background
- If cloud is unavailable, MOON continues operating
- Sync resumes when connectivity returns

---

## 4. Installation

### Local Installation

```bash
# Clone repository
git clone https://github.com/crsuvo100-gif/MOON.git
cd MOON

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Initialize memory
python -c "from app.memory.store import default_db_path; print(default_db_path())"

# Run tests
python -m pytest tests/test_cognitive_memory.py -v

# Start MOON
python main.py terminal
```

### Docker Deployment

```bash
# Build
docker build -t moon-ai .

# Run
docker run -d \
  --name moon \
  -p 8777:8777 \
  -v moon-memory:/home/meow/.moon/memory \
  -e MOON_MEMORY_BACKEND=local \
  moon-ai
```

### Render Deployment

1. Push to GitHub
2. Create Render account
3. New Web Service → Connect repo
4. Settings:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - Environment: Add all required env vars
5. Deploy

---

## 5. Verification

### Test Suite

```bash
# Run all memory tests
python -m pytest tests/test_cognitive_memory.py tests/test_cognitive_memory_full.py \
  tests/test_memory_infrastructure.py tests/test_enhanced_memory.py \
  tests/test_context_budget.py -v

# Expected: 196 passed
```

### Health Check

```bash
# Start MOON
python main.py terminal

# In another terminal, check health
curl http://127.0.0.1:8777/api/memory/health
```

### Memory Operations

```python
from app.memory.cognitive import CognitiveMemoryManager

mgr = CognitiveMemoryManager()

# Store a memory
mgr.store("MOON uses Python 3.14", source_type=SourceType.USER, explicit=True)

# Search
results = mgr.search("Python version", top_k=5)

# Forget
mgr.forget_matching("Python version")
```

---

## 6. Free Tier Limitations & Mitigations

| Platform | Limitation | Mitigation |
|----------|------------|------------|
| Render | 15-min sleep | Use UptimeRobot ping |
| Render | 750 hours/month | Single service only |
| Railway | $5 credit limit | Monitor usage |
| Oracle | Complex setup | Use Docker |

---

## 7. Security Considerations

- All secrets are detected and blocked from memory storage
- Cloud credentials are never exposed via API
- Memory is encrypted in transit (HTTPS)
- Agent memory is isolated by scope
- Retrieved memory is marked as DATA, not instructions

---

## 8. Next Steps

1. Choose deployment platform
2. Configure environment variables
3. Deploy and verify
4. Set up monitoring (optional)
5. Configure backups

---

## References

- Memory Architecture: `app/memory/README.md`
- API Documentation: `app/memory/api.py`
- Test Suite: `tests/test_cognitive_memory*.py`
- Configuration: `.env.example`
