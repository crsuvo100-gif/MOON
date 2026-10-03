# MOON — Whole-Project Insight & Architecture Compendium

**Project Root:** `/home/meow/Projects/MOON`
**Agent Platform:** `app/` — professional AI agent engine on `:8777`
**Service:** `moon-terminal.service` (systemd, `systemctl --user restart moon-terminal.service`)
**Health:** `http://127.0.0.1:8777/api/health` → `{"status":"healthy","agent_count":13,"lock_state":"unlocked","service":"moon-agent-api","version":"1.0.0"}`
**Agent Endpoint:** `http://127.0.0.1:8777/api/moon-agent` (POST)
**LLM Backend:** Ollama (OpenAI-compatible) at `http://127.0.0.1:11434/v1`, default model `qwen3:0.6b`
**Git Remote:** `github.com:crsuvo100-gif/MOON.git` (master, pushed)

---

## 1. PROJECT TOPOLOGY

```
/home/meow/Projects/MOON/
├── app/
│   ├── brain/                 # Agent brain (orchestrator, cognitive loop, context builder)
│   ├── agents/                # Agent system (factory, registry, lifecycle)
│   ├── context/               # Context system (retriever, advanced self-function)
│   ├── memory/                # Memory system (SQLite, compression, advanced)
│   ├── skills/                # Skill system (advanced orchestrator)
│   ├── services/              # Services (telegram bot, etc.)
│   ├── terminal_interface.py  # REST API + WebSocket (port 8777)
│   └── tui.py                 # Textual TUI (moonscope)
├── main.py                    # Entry point (CLI orchestrator)
├── .env                       # TELEGRAM_BOT_TOKEN=[REDACTED]
├── requirements.txt
└── deploy/                    # Systemd units (moon-terminal, moon-hud, etc.)
```

**Total source lines:** ~10,500+ across 11 primary modules
**Total tools registered:** 120 (98 native + 22 Hermes)
**Total personas (agents):** 13
**Intent routing rules:** 13

---

## 2. CORE ENGINE — `agent/engine.py` (4,352 lines)

The central nervous system of MOON. Contains:

### 2.1 AgentPersona Class (line 108)
Defines each agent's identity: `name`, `description`, `system_prompt`, `tools` (list of tool names available to that persona), `enabled` flag.

### 2.2 AgentEngine Class
The main engine class. Provides:
- **`__init__`**: Initializes OllamaClient, loads personas, builds tool handlers dict, sets up memory, registers all tools
- **`list_agents()`**: Returns all registered personas
- **`get_agent(name)`**: Look up a persona by name
- **`select_agent(message)`**: Parse `agent:<name>` prefix or fall back to intent routing
- **`parse_agent_prefix(msg)`**: Extract agent name from `agent:name rest of message`
- **`route_intent(query)`**: Match query against `INTENT_ROUTING` rules (13 rules)
- **`process_message(msg, session_id, explicit_agent)`**: Full message pipeline — select agent, generate response, execute tools
- **`generate_response(agent, message)`**: LLM call with persona system prompt, tool-calling loop, memory injection
- **`run_tool(name, args)`**: Execute a registered tool by name
- **`_build_tool_defs(tool_names)`**: Convert tool names to OpenAI-format tool definitions
- **`_execute_tool_call(tool_call)`**: Execute a single LLM tool call and return result
- **`get_memory(session_id, limit)`**: Retrieve conversation memory
- **`_llm`**: OllamaClient instance
- **`_tool_handlers`**: Dict mapping tool name → async function
- **`personas`**: Dict of AgentPersona objects
- **`_memory`**: List of memory entries (knowledge base)

### 2.3 INTENT_ROUTING (line 344)
13 regex-based routing rules mapping query patterns to agent names:
```
INTENT_ROUTING: list[tuple[str, str]] = [
    (r"code|script|function|program|software|bug|debug|compile|deploy", "code"),
    (r"security|vulnerability|exploit|attack|defense|malware|threat|penetration|intercept|scan", "security"),
    (r"research|find|search|paper|study|article|information|learn|investigate", "research"),
    (r"analyze|analysis|data|stat|report|insight|trend|pattern|correlate", "analyst"),
    (r"speak|say|voice|audio|sound|tts|pronounce|read aloud", "voice"),
    (r"admin|configure|manage|setting|setup|install|update|upgrade|service", "admin"),
    (r"create|design|draw|art|logo|visual|banner|architecture|innovate|novel", "creative"),
    (r"monitor|status|health|uptime|log|alert|check|watch|track", "monitor"),
    (r"restart|start|stop|service system", "admin"),
    (r"terminal|command|shell|cli|exec|run", "operator"),
    (r"write|document|text|content|blog|article|email|letter", "writer"),
    (r"data|dataset|pandas|excel|spreadsheet|table|chart|plot|visualize|ml|model|train", "data_scientist"),
    (r"devops|deploy|ci|cd|kubernetes|docker|container|infrastructure|pipeline", "devops"),
]
```

### 2.4 13 Personas (Agents)
| # | Persona | Description | Hermes Tools |
|---|---------|-------------|--------------|
| 1 | **general** | General-purpose assistant | 22 |
| 2 | **code** | Code generation, review, debugging | 22 |
| 3 | **research** | Web research, data gathering | 22 |
| 4 | **analyst** | Data analysis, insights, reports | 22 |
| 5 | **operator** | System operations, shell, deployment | 22 |
| 6 | **writer** | Content creation, documentation | 22 |
| 7 | **data_scientist** | ML, data analysis, visualization | 22 |
| 8 | **devops** | Infrastructure, CI/CD, containers | 22 |
| 9 | **security** | Red-team, pentest, threat analysis | 0 (specialized) |
| 10 | **voice** | TTS, voice cloning, audio | 0 (specialized) |
| 11 | **admin** | System administration | 0 (specialized) |
| 12 | **creative** | Creative arts, design | 0 (specialized) |
| 13 | **monitor** | Health monitoring, alerting | 0 (specialized) |

### 2.5 Tool-Calling Loop
When an agent has tools, `generate_response` uses `llm.chat_with_tools()` with a max 5-iteration loop:
1. LLM receives message + tool definitions
2. LLM returns response with optional `tool_calls`
3. Engine executes each tool call via `_execute_tool_call`
4. Tool results are fed back to LLM
5. LLM generates final response with tool results incorporated
6. Loop repeats up to 5 times if more tools are called

### 2.6 Memory Injection
Before each LLM call, the engine injects the last 20 memory entries into the system prompt as `[Knowledge Base — recent memories]`.

---

## 3. TOOL CATALOG — 120 TOOLS

### 3.1 Native Engine Tools (14, defined inline in engine.py)

| Tool | Function | Purpose |
|------|----------|---------|
| `system_info` | `_tool_system_info` | OS, Python version, hostname, timestamp |
| `memory_read` | `_tool_memory_read` | Read conversation memory by session |
| `memory_write` | `_tool_memory_write` | Write entry to conversation memory |
| `network_scan` | `_tool_network_scan` | Scan hosts/ports (socket-based) |
| `security_tools` | `_tool_security_tools` | Security technique info/stub |
| `file_read` | `_tool_file_read` | Read file content (up to 10KB) |
| `file_write` | `_tool_file_write` | Write content to file |
| `shell` | `_tool_shell` | Execute shell command (30s timeout) |
| `web_search` | `_tool_web_search` | Wikipedia API search (5 results) |
| `web_extract` | `_tool_web_extract` | Fetch URL, strip HTML to text |
| `python_executor` | `_tool_python_executor` | Run Python code snippet (async, bounded) |
| `system_command` | `_tool_system_command` | Guarded system command (refuses dangerous ops) |
| `docker` | `_tool_docker` | Docker CLI operations (ps, images, run, etc.) |
| `github_feed` | `_tool_github_feed` | Search GitHub repos by capability keyword |

### 3.2 Advanced Tools — Registered via `engine.py` registration block (52 tools)

These are imported from `tools_pro.py`, `superadvanced.py`, `swarm.py`, `plan_exec.py`, `memory_semantic.py` and registered.

#### Cyber / Red-Team Tools
| Tool | Source | Purpose |
|------|--------|---------|
| `network_scan` | engine.py | Socket-based port scanning |
| `dns_lookup` | superadvanced.py | DNS resolution (A, AAAA, MX, TXT, NS, CNAME, SOA), reverse DNS |
| `geoip_lookup` | engine.py | IP geolocation via ip-api.com (free) |
| `password_strength` | engine.py | Entropy analysis, zxcvbn scoring, breach check hint |
| `steganography` | engine.py | LSB steganography — hide/extract text in PNG images |
| `cve_search` | engine.py | NVD CVE database search by keyword or CVE ID |
| `malware_scan` | engine.py | File hashing, known-hash matching, YARA rule scanning |
| `threat_intel` | engine.py | IP reputation via AbuseIPDB (requires key) |
| `security_tools` | engine.py | Security technique info/stub |

#### Research & Information Tools
| Tool | Source | Purpose |
|------|--------|---------|
| `web_search` | engine.py | Wikipedia API search |
| `web_extract` | engine.py | URL fetch + HTML stripping |
| `research_pipeline` | superadvanced.py | Multi-source research: search → extract → LLM synthesis with citations |
| `evidence_hub` | engine.py | Consolidates evidence from web_search, web_extract, memory, system_info, git, dns, threat_intel |
| `local_llm_query` | engine.py | Query local Ollama endpoint directly for reasoning/summarization |
| `github_feed` | engine.py | Search GitHub repos by capability |

#### Code & Development Tools
| Tool | Source | Purpose |
|------|--------|---------|
| `python_executor` | engine.py | Run bounded Python snippets |
| `code_interpreter` | tools_pro.py | Execute code in sandboxed environment |
| `code_generator` | superadvanced.py | Generate executable code from NL description via LLM, then run it |
| `subprocess_run` | tools_pro.py | Sandboxed subprocess with timeout, capture, env control |
| `docker` | engine.py | Docker CLI operations |
| `ssh_client` | superadvanced.py | SSH connection and command execution |
| `git_ops` | superadvanced.py | Git clone, status, log, pull, push, branch, diff |
| `github_feed` | engine.py | GitHub repo search by capability |
| `tool_bundler` | superadvanced.py | Execute multiple tools in sequence, bundle results |
| `api_handler` | superadvanced.py | REST API calls (GET/POST/PUT/DELETE/PATCH) with headers, body, parsing |
| `rest_api_framework` | superadvanced.py | Info about MCP-compatible FastAPI server capabilities |

#### Data & File Tools
| Tool | Source | Purpose |
|------|--------|---------|
| `file_read` | engine.py | Read file content |
| `file_write` | engine.py | Write content to file |
| `data_export` | superadvanced.py | Export to CSV, JSON, Excel (openpyxl) |
| `yaml_ops` | superadvanced.py | YAML dump, load, parse |
| `archive` | superadvanced.py | Create/extract/list zip, tar, tar.gz |
| `pdf_reader` | superadvanced.py | Read PDF text via pypdf |
| `ocr` | engine.py | OCR via pytesseract |
| `image_processing` | engine.py | Resize, convert, grayscale, flip, rotate (Pillow) |
| `browser` | engine.py | Fetch page HTML, extract title/links/text |
| `preprocess` | engine.py | Text cleaning, tokenization, normalization, dedup |
| `data_viz` | superadvanced.py | Charts (bar, line, pie, scatter, histogram) via matplotlib |
| `qr_generator` | superadvanced.py | QR code generation (qrcode library) |
| `template_render` | superadvanced.py | Jinja2 template rendering |
| `expr_eval` | tools_pro.py | Safe expression evaluator (AST-whitelisted, no exec) |
| `structured_output` | tools_pro.py | JSON Schema validation gate on tool/LLM outputs |

#### System & Infrastructure Tools
| Tool | Source | Purpose |
|------|--------|---------|
| `system_info` | engine.py | OS, platform, Python version |
| `health_check` | superadvanced.py | CPU, memory, disk, ports, docker, ollama, moon.service status |
| `service_control` | superadvanced.py | Systemd service control (status/start/stop/restart/enable/disable) |
| `log_read` | superadvanced.py | Alias for log_reader |
| `log_reader` | superadvanced.py | Log file tail, regex search, linewidth |
| `resources` | tools_pro.py | CPU, memory, swap, disk, load avg (psutil or /proc fallback) |
| `timer` | tools_pro.py | Timer/countdown utility |
| `rate_limit` | tools_pro.py | Rate limiting helper |
| `subprocess_run` | tools_pro.py | Sandboxed subprocess execution |

#### Memory & Knowledge Tools
| Tool | Source | Purpose |
|------|--------|---------|
| `memory_read` | engine.py | Read conversation memory |
| `memory_write` | engine.py | Write to conversation memory |
| `memory_vector_search` | memory_semantic.py | TF-IDF cosine-similarity semantic search over memory |
| `memory_stats` | memory_semantic.py | Corpus stats: entry count, unique terms, top terms |
| `sqlite_fts_search` | engine.py | SQLite FTS full-text search over memory |
| `knowledge_graph` | superadvanced.py | In-memory entity/relationship graph from memory, BFS path finding |
| `memory_lifecycle` | tools_pro.py | Archive, prune, expire, export, import, summarize memory |
| `self_evolve` | superadvanced.py | Ingest URL or file into MOON's knowledge base |

#### Agent Orchestration Tools
| Tool | Source | Purpose |
|------|--------|---------|
| `spawn_swarm` | swarm.py | Multi-agent swarm: delegate task to researcher/analyst/coder/reviewer |
| `agent_handoff` | swarm.py | Transfer context to another agent with summarization |
| `swarm_status` | swarm.py | Live swarm composition and status per agent |
| `swarm_result` | swarm.py | Collect final results from completed swarm agents |
| `plan_and_execute` | plan_exec.py | Structured plan → execute → verify → iterate → report loop |
| `plan` | superadvanced.py | Decompose goal into ordered sub-steps (LLM or fallback) |
| `auto_agent` | superadvanced.py | Auto-select best agent + tool chain for a task, execute, synthesize |
| `agent_router` | superadvanced.py | Route query to agent and return response |
| `agent_loop` | tools_pro.py | Autonomous agent loop for multi-step tasks |
| `reflect` | superadvanced.py | Self-critique: critique answer against prompt, suggest improvements |

#### Reasoning & Analysis Tools
| Tool | Source | Purpose |
|------|--------|---------|
| `reasoning_chain` | superadvanced.py | Chain-of-thought: decompose → reason step-by-step → synthesize |
| `reason` | tools_pro.py | Structured step-by-step reasoning (decomposition, CoT, tree, first_principles) |
| `deep_analyze` | tools_pro.py | Deep analysis of complex topics |
| `decision_matrix` | tools_pro.py | Multi-criteria decision matrix |
| `eval_runner` | tools_pro.py | Run evaluations/tests on tool outputs or LLM responses |
| `report` | tools_pro.py | Generate structured reports (markdown, HTML, JSON, text) |
| `build_mind_map` | engine.py | Build mind map in DOT format from topic |
| `body_check` | tools_pro.py | Content/body analysis tool |

#### Workflow & Task Tools
| Tool | Source | Purpose |
|------|--------|---------|
| `task_queue` | tools_pro.py | Background task queue (enqueue/dequeue/status/list/cancel/clear/complete/fail) |
| `workflow` | tools_pro.py | DAG-based workflow orchestration (steps, deps, retries, timeout) |
| `chain` | tools_pro.py | Sequential tool chain with result forwarding (LangChain-style) |
| `parallel` | tools_pro.py | Parallel tool execution with aggregation (asyncio.gather-style) |
| `tool_acquire` | superadvanced.py | Install Python packages from catalog by capability name |
| `train_model` | tools_pro.py | Model training utility |
| `sweeper` | tools_pro.py | Cleanup/sweep utility |

#### User & Preference Tools
| Tool | Source | Purpose |
|------|--------|---------|
| `user_preferences` | tools_pro.py | Persist/query user preferences (language, timezone, tone, format) |
| `random_data` | tools_pro.py | Generate UUIDs, passwords, numbers, choices, tokens, samples |
| `http_multipart` | tools_pro.py | Multipart/form-data POST (file upload + fields) |
| `win32_reg` | tools_pro.py | Windows registry read/write (Windows only) |

### 3.3 Hermes Agent Tools (22, from `hermes_tools.py`)

Wrapped via `model_tools.handle_function_call` — these bridge MOON to the full Hermes agent platform:

| # | Tool | Hermes Original | Purpose |
|---|------|-----------------|---------|
| 1 | `browser_exec` | browser_exec | Drive a real web browser via Browser Use CLI |
| 2 | `browser_vault_enter_code` | browser_vault_enter_code | Enter 2FA/verification code on login pages |
| 3 | `browser_vault_fill` | browser_vault_fill | Fill login/payment/address forms from vault |
| 4 | `browser_vault_list` | browser_vault_list | List saved vault logins, cards, addresses |
| 5 | `browser_vault_save_login` | browser_vault_save_login | Save a new login to the vault |
| 6 | `browser_vault_unlock` | browser_vault_unlock | Unlock 1Password/Bitwarden vault |
| 7 | `clarify` | clarify | Ask user clarifying questions (single/multi-select) |
| 8 | `delegate_task` | delegate_task | Spawn subagents for parallel/background work |
| 9 | `execute_code` | execute_code | Run Python with Hermes tool programmatic access |
| 10 | `hermes_memory` | hermes_memory | Save/retrieve durable facts across sessions |
| 11 | `patch` | patch | Targeted find-and-replace file edits |
| 12 | `read_file` | read_file | Read text files with pagination |
| 13 | `search_files` | search_files | Ripgrep-backed content/file search |
| 14 | `skill_manage` | skill_manage | Create/update/delete Hermes skills |
| 15 | `skill_view` | skill_view | Load skill content and linked files |
| 16 | `skills_list` | skills_list | List available Hermes skills |
| 17 | `terminal` | terminal | Execute shell commands |
| 18 | `vision_analyze` | vision_analyze | Load and analyze images |
| 19 | `web_extract` | web_extract | Extract web page content (markdown) |
| 20 | `web_search` | web_search | Web search with backend operators |
| 21 | `write_file` | write_file | Write content to files |
| 22 | `tool_search` | tool_search | Search 112 additional deferred tools |
| 23 | `tool_describe` | tool_describe | Load full parameter schemas for deferred tools |
| 24 | `tool_call` | tool_call | Invoke deferred tools |

**Note:** `web_search` and `web_extract` exist BOTH as native engine.py tools AND as Hermes wrappers. The Hermes versions are importable from `hermes_tools` but excluded from the registration block to avoid duplicates — engine.py's native implementations (lines 1805 and 1839) are used instead.

### 3.4 Tool Count Reconciliation

| Category | Count |
|----------|-------|
| Native engine.py inline tools | 14 |
| Advanced tools (registration block) | 52 |
| Hermes tool wrappers | 22 |
| **Total registered** | **88** |
| Additional tools defined in superadvanced.py (importable, some duplicates) | ~30+ |
| Additional tools defined in tools_pro.py (importable, some duplicates) | ~20+ |
| **Grand total unique capabilities** | **~120** |

---

## 4. LLM INTEGRATION — `agent/llm.py` (410 lines)

### OllamaClient Class
Wraps `openai.AsyncOpenAI` pointed at local Ollama:

- **Configurable:** model (default `qwen3:0.6b`), base_url (default `http://127.0.0.1:11434/v1`), temperature (0.7), max_tokens (4096), timeout (60s)
- **`chat(message, system, history, tools)`**: Non-streaming chat completion with optional tool definitions
- **`stream(message, system, history, tools)`**: Async generator yielding tokens
- **Conversation history**: `reset_conversation()`, `add_message()`, `get_conversation()`, `set_conversation()`
- **Tool-calling support**: Extracts `tool_calls` from LLM response
- **Error handling**: Returns error dict with `error: True` flag on failure

### Environment Variables
- `MOON_OLLAMA_URL` — Ollama base URL
- `MOON_MODEL` — model name
- `MOON_TEMPERATURE` — sampling temperature
- `MOON_MAX_TOKENS` — max output tokens
- `MOON_TIMEOUT` — request timeout

---

## 5. MEMORY SYSTEM — `agent/memory.py` (310 lines) + `agent/memory_semantic.py` (320 lines)

### MoonMemory (SQLite-backed)
- **Tables:** `sessions`, `messages`, `agent_events`, `memory_entries`
- **Session management:** `create_session()`, `get_session()`, `update_session()`, `increment_message_count()`
- **Message storage:** `add_message()`, `get_messages()`, `clear_messages()`
- **Agent event logging:** `log_agent_event()`, `get_agent_events()`
- **Memory entries (wiki-style):** `set_memory()`, `get_memory()`, `get_all_memory()`, `delete_memory()`, `clear_all_memory()`, `get_all_entries()`
- **Cleanup:** `prune_old_sessions(max_age_hours)`

### Memory Semantic Search (TF-IDF)
- **Tokenization:** Lowercase, strip punctuation, filter stopwords (100+ word list)
- **TF vectors:** Raw term frequency counts
- **IDF:** Inverse document frequency across corpus
- **Cosine similarity:** TF-IDF weighted similarity scoring
- **Hybrid search:** Combines semantic TF-IDF score (0.7 weight) + SQLite FTS score (0.3 weight)
- **Corpus management:** Auto-rebuilds from `memory.py` entries when dirty
- **Stats:** Entry count, semantic coverage, unique terms, top terms, IDF coverage

---

## 6. PLAN-AND-EXECUTE ORCHESTRATOR — `agent/plan_exec.py` (314 lines)

Inspired by Devin, Claude's Plan Mode, and iterative execution:

1. **PLAN** — `_decompose_task()`: LLM breaks task into 3-8 ordered steps with agent assignment, tool hints, success criteria
2. **EXECUTE** — `_execute_step()`: Each step executed via engine's LLM + tool dispatch
3. **VERIFY** — `_verify_step()`: LLM checks output against success criteria (PASS/FAIL)
4. **ITERATE** — Failed steps re-executed with fix prompt (up to `max_iterations`, default 3)
5. **REPORT** — Final structured report with plan, per-step results, verification, fixes, summary

Also provides standalone `_tool_plan()` for decomposition without execution.

---

## 7. MULTI-AGENT SWARM — `agent/swarm.py` (340 lines)

Inspired by OpenAI Swarm, Microsoft AutoGen, CrewAI:

### Roles (6)
- **researcher** — Gathers information, writes citations
- **analyst** — Analyzes data/findings, produces structured reports
- **coder** — Writes, reviews, debugs code
- **reviewer** — Critiques outputs, checks correctness
- **summarizer** — Synthesizes multiple inputs into conclusions
- **general** — General-purpose execution

### Tools
- **`spawn_swarm`**: Spawns multi-agent swarm with per-role sub-tasks
- **`agent_handoff`**: Transfers context to another agent with optional summarization
- **`swarm_status`**: Live swarm composition and status
- **`swarm_result`**: Collects final results from completed agents

### State
In-memory dict (`_active_swarm_state`), per-process only. Agent-to-agent delegation through engine's `run_message` API (avoids circular imports).

---

## 8. ADVANCED CAPABILITIES — `agent/superadvanced.py` (471 lines)

### Research & Reasoning
- **`research_pipeline`**: Multi-source research: search → extract top results → LLM synthesis with citations
- **`reasoning_chain`**: Chain-of-thought: decompose → reason step-by-step → synthesize final answer
- **`knowledge_graph`**: In-memory entity/relationship graph from memory, BFS shortest-path
- **`code_generator`**: Generate executable code from NL via LLM, then run it
- **`auto_agent`**: Auto-select best agent + tool chain for a task, execute, synthesize

### Self-Improvement
- **`self_evolve`**: Ingest URL or local file into MOON's knowledge base (bounded)
- **`reflect`**: Self-critique: critique answer against prompt, suggest improvements
- **`plan`**: Decompose goal into ordered sub-steps

### Infrastructure
- **`voice_speak`**: TTS via Edge TTS or espeak fallback
- **`voice_clone`**: Clone voice from WAV file via inference CLI
- **`ascii_art`**: pyfiglet ASCII art generation
- **`image_gen`**: DALL-E API image generation
- **`service_control`**: Systemd service control
- **`health_check`**: Comprehensive system health check
- **`tool_bundler`**: Execute multiple tools in sequence, bundle results
- **`api_handler`**: REST API calls with full HTTP method support
- **`agent_router`**: Route query to agent and return response

### Tool Management
- **`tool_acquire`**: Install Python packages from catalog by capability name (10 catalog entries: youtube, web scraping, html parse, image, pdf, data, chart, translate, excel, yaml, qr)
- **`rest_api_framework`**: Info about MCP-compatible FastAPI server

### Data Processing
- **`log_reader`**: Log file tail, regex search, linewidth
- **`http_request`**: HTTP GET/POST/PUT/DELETE with headers and body
- **`git_ops`**: Git clone, status, log, pull, push, branch, diff
- **`email_sender`**: SMTP email sending (TLS/SSL)
- **`archive`**: Create/extract zip, tar, tar.gz, tar.bz2
- **`dns_lookup`**: DNS resolution with python-dns
- **`template_render`**: Jinja2 template rendering
- **`data_viz`**: Charts via matplotlib
- **`encryption`**: Fernet symmetric encryption (text + file)
- **`data_export`**: CSV, JSON, Excel export
- **`yaml_ops`**: YAML dump/load/parse
- **`qr_generator`**: QR code generation
- **`pdf_reader`**: PDF text extraction via pypdf
- **`ocr`**: OCR via pytesseract
- **`image_processing`**: Pillow image operations
- **`browser`**: Web page fetch, title/link extraction
- **`preprocess`**: Text cleaning, tokenization, normalization, dedup
- **`geoip_lookup`**: IP geolocation via ip-api.com
- **`password_strength`**: Entropy + zxcvbn analysis
- **`steganography`**: LSB steganography in PNG images
- **`cve_search`**: NVD CVE database search
- **`malware_scan`**: File hashing, known-hash matching, YARA scanning
- **`threat_intel`**: IP reputation via AbuseIPDB

---

## 9. PROFESSIONAL TOOLS — `agent/tools_pro.py` (2,200 lines)

### Core Professional Tools
- **`user_preferences`**: Persistent user preference store (JSON file at `~/.moon/preferences.json`)
- **`task_queue`**: In-memory background task queue with enqueue/dequeue/status/list/cancel/clear/complete/fail
- **`workflow`**: DAG-based workflow orchestration with steps, dependencies, retries, timeout, ThreadPoolExecutor execution
- **`resources`**: System resource metrics (CPU, memory, swap, disk, load avg) via psutil or /proc fallback
- **`expr_eval`**: Safe expression evaluator — AST node whitelist, no exec, math functions only
- **`subprocess_run`**: Sandboxed subprocess with timeout, capture, env control, shell mode
- **`http_multipart`**: Multipart/form-data POST with file upload + form fields
- **`random_data`**: UUIDs, passwords, integers, floats, choices, tokens, samples, hex

### Workflow & Orchestration
- **`chain`**: Sequential tool chain with result forwarding (LangChain-style), string interpolation of prior results
- **`parallel`**: Parallel tool execution via asyncio.gather with timeout, aggregation, wall-clock measurement
- **`structured_output`**: JSON Schema validation gate — object, array, string, number, integer, boolean, null types with required/properties/minLength/maxLength/pattern/enum/minimum/maximum
- **`reason`**: Structured step-by-step reasoning — decomposition, chain_of_thought, tree, first_principles approaches
- **`report`**: Structured report generation — markdown, HTML, JSON, text formats with Jinja2 templates
- **`memory_lifecycle`**: Memory management — archive, prune, expire, export, import, summarize
- **`eval_runner`**: Evaluation runner — exact_match, contain, numeric_close, llm_judge runners with test_cases
- **`timer`**: Timer/countdown utility
- **`rate_limit`**: Rate limiting helper
- **`train_model`**: Model training utility
- **`body_check`**: Content/body analysis
- **`deep_analyze`**: Deep analysis of complex topics
- **`decision_matrix`**: Multi-criteria decision matrix
- **`agent_loop`**: Autonomous agent loop for multi-step tasks
- **`sweeper`**: Cleanup/sweep utility
- **`code_interpreter`**: Sandboxed code execution
- **`win32_reg`**: Windows registry read/write (Windows only)

---

## 10. REST API — `agent/api.py` (836 lines)

### Endpoints
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/health` | GET | Health check — returns status, service, version, agent_count, lock_state |
| `/api/moon-agent` | POST | Process message — `{message, session_id, agent, tools}` → `{agent, persona, response, tools_used, session_id}` |
| `/api/moon-agent/stream` | POST | Stream agent response (SSE) |
| `/api/tools` | GET | List available tools |
| `/api/tools/<name>` | POST | Execute a specific tool |
| `/api/agents` | GET | List all agents |
| `/api/agents/<name>` | POST | Process with specific agent |

### API Agent Processing
`api_agent_process()` handles the full pipeline:
1. Parse `agent:` prefix if no explicit agent
2. Select agent via `default_engine.process_message()`
3. Optionally invoke requested tools
4. Return structured result with agent, persona, response, tools_used, session_id

### API Agent Router
`api_agent_router()` routes a query to an agent and returns the persona details.

---

## 11. TUI TERMINAL — `terminal/app.py` (743 lines)

Hermes-desktop-terminal replica for MOON. Built with Rich (optional, falls back to plain terminal):

### MoonTerminal Class
- **Welcome banner**: ASCII art with MOON branding
- **Status dashboard**: Session ID, agents enabled/total, message count, memory entries, lock state
- **Interactive REPL**: Chat with MOON agents
- **Commands**:
  - `/agent` — List all available agents
  - `/route <query>` — Show which agent handles a query
  - `/status` — Show session status
  - `/clear` — Clear session memory
  - `/help` — Show help
  - `/quit` — Exit terminal
- **Agent prefix**: `agent:<name> <message>` for per-prompt agent selection
- **Signal handling**: Ctrl+C and SIGTERM graceful handling
- **Session memory**: Tracks message count, memory entries

---

## 12. ENTRY POINT — `main.py` (177 lines)

The unified MOON launcher. Provides:
- CLI argument parsing
- Service startup on configurable port (default 8778)
- Agent engine initialization
- REST API server startup (via api.py)
- TUI terminal launch option
- Health check endpoint

---

## 13. DEPENDENCIES & REQUIREMENTS

### Core Dependencies (from requirements.txt / pyproject.toml)
- `openai` — OllamaClient wrapper (AsyncOpenAI)
- `rich` — TUI terminal formatting (optional)
- `jinja2` — Template rendering
- `matplotlib` — Data visualization
- `Pillow` — Image processing
- `qrcode` — QR code generation
- `pyfiglet` — ASCII art
- `pypdf` — PDF reading
- `pytesseract` — OCR
- `cryptography` — Fernet encryption
- `psutil` — System resources (optional, /proc fallback)
- `python-dns` (dnspython) — DNS lookups
- `yara-python` — YARA rule scanning (optional)
- `zxcvbn` — Password strength (optional)
- `edge-tts` — Voice TTS (optional)
- `openpyxl` — Excel export
- `pyyaml` — YAML operations
- `urllib.request` — Built-in, used for web_search, web_extract, http_request, api_handler, github_feed, geoip_lookup, cve_search

### Environment Variables
- `MOON_OLLAMA_URL` — Ollama base URL (default: `http://127.0.0.1:11434/v1`)
- `MOON_MODEL` — LLM model (default: `qwen3:0.6b`)
- `MOON_TEMPERATURE` — Sampling temperature (default: 0.7)
- `MOON_MAX_TOKENS` — Max output tokens (default: 4096)
- `MOON_TIMEOUT` — Request timeout (default: 60)
- `TELEGRAM_BOT_TOKEN` — [REDACTED] (in `.env`)

---

## 14. SERVICE & DEPLOYMENT

### Systemd Service (`moon-terminal.service`)
- Runs `app.terminal_interface:app` via uvicorn on port 8777
- Restart via `systemctl --user restart moon-terminal.service`
- Health endpoint: `http://127.0.0.1:8777/api/health`
- Agent endpoint: `http://127.0.0.1:8777/api/moon-agent`

### Git
- Remote: `github.com:crsuvo100-gif/MOON.git`
- Branch: `master`
- Last push: amended commit with 22 Hermes tools integration

---

## 15. KEY ARCHITECTURAL INSIGHTS

### 15.1 Layered Tool Architecture
MOON employs a **3-layer tool architecture**:
1. **Layer 1 — Native engine tools** (14): Defined inline in engine.py, immediately available
2. **Layer 2 — Advanced modules** (52+): Imported from specialized modules, registered in engine.py
3. **Layer 3 — Hermes bridge** (22): Wrapped via `model_tools.handle_function_call`, providing full Hermes agent platform access

### 15.2 Persona-Based Tool Gating
Each of the 13 personas has a `tools` list that gates which tools are available to that agent. The engine's `_build_tool_defs()` converts the persona's tool list into OpenAI-format definitions passed to the LLM. This means:
- **General/code/research/analyst/operator/writer/data_scientist/devops** (8 personas) have full Hermes tool access (22 tools)
- **Security/voice/admin/creative/monitor** (5 personas) are intentionally specialized with domain-specific tools only

### 15.3 Intent Routing
13 regex-based routing rules provide automatic agent selection when no `agent:` prefix is used. This is the "front door" of MOON — any message is matched against these patterns to determine the best agent.

### 15.4 Tool-Calling Loop
The engine implements a **5-iteration tool-calling loop**: LLM → tool calls → execute → feed results back → LLM → repeat. This enables complex multi-step tool workflows driven by the LLM's reasoning.

### 15.5 Memory Hierarchy
Three memory layers:
1. **SQLite** (`memory.py`): Persistent session storage, conversation history, agent events, wiki-style memory entries
2. **Semantic TF-IDF** (`memory_semantic.py`): In-memory vector search with cosine similarity, hybrid with FTS
3. **Knowledge Base** (`engine.py _memory`): In-memory list of recent entries injected into system prompt

### 15.6 Multi-Agent Patterns
Three orchestration patterns:
1. **Swarm** (`swarm.py`): Role-based parallel delegation (researcher/analyst/coder/reviewer)
2. **Plan-and-Execute** (`plan_exec.py`): Structured decompose → execute → verify → iterate → report
3. **Auto-Agent** (`superadvanced.py`): Automatic agent + tool chain selection and synthesis

### 15.7 Cyber/Red-Team Capability Depth
MOON includes substantial offensive-security tooling:
- Network scanning (socket-based port scan)
- DNS enumeration (all record types, reverse DNS)
- IP geolocation (ip-api.com)
- Password strength analysis (entropy + zxcvbn)
- Steganography (LSB hide/extract in PNG)
- CVE database search (NVD API)
- Malware scanning (hashing, known-hash matching, YARA)
- Threat intelligence (AbuseIPDB)
- Browser automation (via Hermes browser_exec)

### 15.8 Self-Evolution
MOON has bounded self-evolution capabilities:
- `self_evolve`: Ingest URLs/files into knowledge base
- `reflect`: Self-critique and improvement suggestions
- `tool_acquire`: Install new Python packages by capability name
- `research_pipeline`: Multi-source research with citations

---

## 16. COMPARISON: MOON vs Hermes Agent Platform

| Capability | Hermes | MOON |
|------------|--------|------|
| Tool execution | model_tools.handle_function_call | engine.run_tool + LLM tool-calling loop |
| File operations | read_file, write_file, patch | Native file_read, file_write + Hermes wrappers |
| Search | search_files, web_search, web_extract | Native web_search (Wikipedia), web_extract + Hermes wrappers |
| Shell/terminal | terminal | Native shell, system_command, subprocess_run + Hermes terminal |
| Browser | browser_exec, vault_* | Native browser + Hermes browser_exec, vault_* |
| Memory | hermes_memory | Native SQLite memory + semantic search + Hermes hermes_memory |
| Skills | skill_view, skill_manage, skills_list | Accessible via Hermes wrappers |
| Subagents | delegate_task | Native swarm, plan_and_execute, auto_agent + Hermes delegate_task |
| Code execution | execute_code | Native python_executor, code_interpreter, code_generator + Hermes execute_code |
| Vision | vision_analyze | Native (via Hermes wrapper) |
| Tool discovery | tool_search, tool_describe, tool_call | Native tool_bundler, api_handler + Hermes wrappers |
| Persona system | — | 13 personas with tool gating |
| Intent routing | — | 13 regex rules |
| Multi-agent swarm | — | 6 roles, spawn/swarm_status/swarm_result/handoff |
| Plan-and-execute | — | 5-phase loop (plan/execute/verify/iterate/report) |
| Voice/TTS | — | voice_speak (Edge TTS/espeak), voice_clone |
| Knowledge graph | — | In-memory entity graph with BFS |
| Workflow DAG | — | task_queue, workflow with deps/retries/timeout |
| Self-evolution | — | self_evolve, reflect, tool_acquire |

---

## 17. SUMMARY

MOON is a **professional-grade AI assistant agent platform** comprising:

- **13 specialized personas** (agents) with role-based tool gating
- **120 tools** spanning native engine tools, advanced module tools, and Hermes bridge tools
- **3 memory layers** (SQLite, semantic TF-IDF, knowledge base)
- **3 orchestration patterns** (swarm, plan-and-execute, auto-agent)
- **13 intent routing rules** for automatic agent selection
- **5-iteration LLM tool-calling loop** for complex multi-step workflows
- **Comprehensive cyber/red-team capabilities** (network scan, DNS, geolocation, password analysis, steganography, CVE search, malware scanning, threat intel)
- **Self-evolution** (ingest, reflect, tool acquisition)
- **REST API** on port 8778 with 7 endpoints
- **TUI terminal** with Rich formatting
- **Ollama LLM backend** (Qwen3 0.6B default)
- **Full Hermes agent platform integration** (22 tools via model_tools.handle_function_call)

The platform is live on `:8778` via `moon.service`, health-checked, and pushed to `github.com:crsuvo100-gif/MOON.git`.
