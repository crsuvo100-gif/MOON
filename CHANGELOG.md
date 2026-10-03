# MOON — Changelog

## [Unreleased]

### Added
- 50+ specialist agents across 8 categories (cyber, research, coding, security, voice, admin, creative, monitor)
- 120 tools across 3 tiers (core, professional, advanced)
- Three-layer memory system (conversation, workspace SQLite, semantic TF-IDF)
- Multi-agent swarm orchestration with 6 roles
- Plan-and-execute loop with 5 phases
- Full REST API (7 endpoints)
- TUI terminal interface with command palette
- Female voice TTS (espeak f5 + SoX timbre chain)
- Microphone dictation with Vosk
- ASCII art generation (pyfiglet, cowsay, boxes, unicode)
- Image generation (Pillow, matplotlib)
- QR code generation
- PDF tools (pypdf)
- OCR (pytesseract)
- Web research pipeline with curl fallback
- Knowledge graph / semantic memory
- Structured output tools (json_schema, xml_schema, yaml_schema, csv_schema)
- Task queue with priority scheduling
- Workflow DAG executor
- Decision matrix tool
- Chain tool (sequential tool chaining)
- Parallel tool execution
- Report generation (Markdown, HTML, PDF, JSON)
- Evaluation runner
- Resource inventory tool
- Subprocess execution tool
- HTTP multipart upload tool
- Random data generation tool
- Expression evaluation tool
- chain-of-thought reasoning tool
- 13 personas with intent routing
- RUNLEVEL-based capability gating
- Permission levels on all tools
- systemd user service with auto-start + self-heal
- Deep monitor (every 15 min) verifying real HTTP response
- One-command installer (install.sh + install_moon_full.py)
- Setup wizard for first-run configuration
- Ollama model integration (primary) + OpenAI fallback
- 130 tests (unit, integration, agent, tool, runtime, security, e2e)
- CI/CD via GitHub Actions (Python 3.11 + 3.13 matrix)
- Portable across Linux/macOS
- Comprehensive documentation (README, Installation, Configuration, Architecture, Usage, Development, Troubleshooting, Security)

### Changed
- Consolidated MOON to single canonical checkout at /home/meow/Projects/MOON
- All systemd units + launcher + desktop entry repointed to canonical path
- HUD owned by moon-hud.service; moon-monitor.timer only health-checks


---

## [1.0.0] — Initial Release

- Core agent engine with 13 personas
- 13 intent routing rules
- Tool-calling loop with observation and error recovery
- 120 tools across core/pro/advanced tiers
- 50+ specialist agents
- Three-layer memory system
- Multi-agent swarm
- Plan-and-execute loop
- REST API
- TUI terminal
- Voice TTS
- systemd service
- One-command installer
- 130 tests
- Full documentation
