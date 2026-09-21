# Integration Plan — MOON Master Completion Task 2

## Goal
Wire existing but disconnected components into the live MOON system, preserving all working functionality. Work incrementally, validate every change.

## Current State (Verified)
- Backend: HEALTHY 8/8, 39 agents, 43 tools, qwen3:0.6b
- CapabilityManager: functional (discover, search_github, list_capabilities)
- GlobalConnector: functional (gateway, ConnectionRecord, permission checks)
- VoiceEngine: functional (espeak backend, 5 voices, cloning ready)
- EventBus: functional (publish/subscribe)
- SkillSystem: functional (list_ids, load_skill)
- All 132 tests pass
- Systemd service: running on port 8777

## Integration Work

### 1. Add API Endpoints (backend)
Add to `app/terminal_interface.py`:
- `GET /api/capabilities` — CapabilityManager.list_capabilities()
- `GET /api/connections` — ConnectionGateway.list()
- `GET /api/voice/status` — VoiceEngine.backend_status()

### 2. Frontend Integration Status Display
Add small status indicators in the CORE panel showing:
- Capabilities: N registered
- Connections: N active  
- Voice: backend state

### 3. Wire EventBus to Frontend Event Stream
Forward EventBus.publish() events to the WS event stream so the frontend EVENTS tab shows real-time system events.

### 4. Make Tool Registry Entries Actually Usable
Ensure CapabilityManagerTool and GlobalConnectorTool can be called via the `tool` WS action and return real results.

## Execution Order
1. Backend API endpoints (non-breaking, additive)
2. Frontend status display (uses new endpoints)
3. EventBus wiring
4. Tool registry verification
5. Full system test after each change
