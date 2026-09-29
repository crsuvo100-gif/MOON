# MOON — Usage Guide

## Starting MOON

```bash
# After install:
moon terminal

# Or directly:
./venv/bin/python main.py terminal

# As a service (if systemd installed):
systemctl --user status moon-terminal.service
```

## Terminal Commands

Once in the terminal, type naturally — MOON understands plain English requests.

```
You: What agents are available?
MOON: I have 50 specialist agents across 8 categories...

You: List all tools you have
MOON: I have 120 tools: 14 core, 52 professional, 22 advanced...

You: Use the research agent to find info about X
MOON: [runs research agent, returns findings]

You: Help me write a Python script to do Y
MOON: [coding agent generates code, explains it]
```

### Special Commands

| Command | Description |
|---------|-------------|
| `/agent <name>` | Switch to a specific agent |
| `/route <intent>` | Force a specific intent route |
| `/status` | Show current agent, model, memory status |
| `/clear` | Clear conversation context |
| `/help` | Show available commands |
| `/models` | List available Ollama models |

---

## REST API

MOON exposes a REST API on port 8777 (configurable via `MOON_PORT`).

### Health

```bash
curl http://127.0.0.1:8777/api/health
# {"status":"healthy","service":"moon-agent-api","version":"1.0.0","agent_count":50}
```

### Send a Message

```bash
curl -X POST http://127.0.0.1:8777/api/moon-agent \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello MOON", "agent": "general"}'
```

### Streaming Response

```bash
curl -X POST http://127.0.0.1:8777/api/moon-agent/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "Explain quantum computing", "agent": "research"}'
```

### List Tools

```bash
curl http://127.0.0.1:8777/api/tools
```

### Get a Specific Tool

```bash
curl http://127.0.0.1:8777/api/tools/<tool_name>
```

### List Agents

```bash
curl http://127.0.0.1:8777/api/agents
```

### Get a Specific Agent

```bash
curl http://127.0.0.1:8777/api/agents/<agent_name>
```

---

## Voice Interaction

### Typed + Voice Output

```bash
make voice
# Type a message, MOON replies in female voice
```

### With Microphone (requires vosk)

```bash
export VOSK_MODEL_DIR=/path/to/vosk-model
make voice -- --mic
```

### Voice Presets

| Preset | Character |
|--------|-----------|
| `default` | Warm, friendly, natural |
| `seductive` | Deeper, intimate |
| `warm` | Soft, comforting |
| `crystal` | Clear, bright |

---

## Web HUD (Neural Brain Command Center)

Open `http://127.0.0.1:8777` in a browser. The HUD shows:
- Brain mesh visualization (Three.js)
- Connected-agent mesh
- Live cognition channel (WebSocket)
- Agent status panel

---

## Common Workflows

### Research a Topic

```
You: Research the latest on WebAssembly security
MOON: [research agent → web search → synthesize → report]
```

### Generate Code

```
You: Write a Python script that scans a network for open ports
MOON: [coding agent → generates script → explains it → offers to save it]
```

### Analyze a File

```
You: Read /etc/passwd and tell me what you see
MOON: [file agent → reads → analyzes → reports]
```

### Run a Security Scan

```
You: Do a port scan on 192.168.1.0/24
MOON: [cyber agent → nmap → reports open ports]
```

### Multi-Step Task

```
You: Set up a new project: create a directory, init git, write a README
MOON: [plans → executes each step → verifies → reports]
```

---

## Managing Agents

```bash
# List all agents
curl http://127.0.0.1:8777/api/agents

# Switch agent in terminal
/agent coding

# Check status
curl http://127.0.0.1:8777/api/health
```

---

## Monitoring

```bash
# Service status
systemctl --user status moon-terminal.service

# Recent logs
journalctl --user -u moon-terminal.service -n 50

# Deep monitor check (every 15 min)
systemctl --user status moon-monitor.timer
```
