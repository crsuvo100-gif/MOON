# MOON — Security Guide

## Security Model

MOON is designed to operate within a defined **safety boundary**. By default, MOON is authorized to act on systems and targets that belong to the operator. Actions against non-owned targets require explicit authorization.

### Safety Boundary

The safety boundary is configured in `.env` via `MOON_SAFETY_boundary`. This defines the scope within which MOON may operate autonomously. Targets outside this boundary are blocked unless explicitly authorized.

### RUNLEVEL Gating

MOON uses a RUNLEVEL system to gate capabilities:

| RUNLEVEL | Description |
|----------|-------------|
| `SAFE` | Read-only, informational, no side effects |
| `ANALYZE` | Analysis and assessment, no exploitation |
| `AUTHORIZED_OPS` | Active operations against authorized targets only |
| `BLOCKED` | Capabilities blocked entirely |

---

## What MOON Can Do

### Within Safety Boundary (Authorized)

- Network scanning (port scans, service enumeration) on owned infrastructure
- Vulnerability analysis on owned systems
- Web research and OSINT on public information
- File operations on local files
- Code generation and execution (with sandboxing where applicable)
- API interaction (with explicit authorization)
- Voice interaction
- Memory consolidation and learning

### Blocked by Default

- Actions against non-owned targets without explicit authorization
- Exploitation of systems the operator does not own
- Any action the operator has not explicitly allowed
- Hard-coded credentials or secrets
- Unauthorized data exfiltration

---

## Security Features

### No Hard-Coded Secrets

All credentials are environment variables. `.env` is git-ignored. The setup wizard prompts for required configuration without storing secrets in the repo.

### Permission Levels on Tools

Every tool has a permission level. The engine checks permissions before executing tools. High-risk tools require elevated RUNLEVEL.

### Input Validation

All inputs are validated before processing. Malformed or suspicious inputs are rejected.

### Error Handling

Errors are logged, never silently swallowed. Failures are reported to the user.

### Audit Logging

All tool executions, agent actions, and significant events are logged for audit purposes.

---

## Securing Your MOON Installation

### 1. Configure the Safety Boundary

On first run, the setup wizard asks for your safety boundary. Set this to your organization/domain.

### 2. Protect .env

```bash
chmod 600 .env
```

`.env` contains your API keys and configuration. Keep it private.

### 3. Run as a Non-Root User

MOON runs as a user service (systemd `--user`). It should never run as root.

### 4. Network Exposure

By default, MOON binds to localhost (127.0.0.1). Do not expose the API port to the public internet without authentication.

### 5. Model Isolation

MOON uses Ollama for local inference. Ollama runs locally and should not be exposed publicly.

---

## Security Audit

A security audit of MOON's codebase is conducted as part of the build process. The audit covers:

- Hard-coded secrets and credentials
- Input validation gaps
- Permission bypass vulnerabilities
- Unsafe execution paths
- Data exposure risks
- Insecure defaults

See the compilation document (`MOON_WHOLE_PROJECT_INSIGHT.md`) for the full security audit findings.

---

## Responsible Use

MOON is a powerful tool. Use it responsibly:

- Only scan systems you own or have explicit permission to test
- Only access data you are authorized to access
- Only run operations within your safety boundary
- Report findings responsibly

MOON is designed for authorized security work, research, automation, and productivity. It is not designed for unauthorized access, data theft, or malicious activity.
