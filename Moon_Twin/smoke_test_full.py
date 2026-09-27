import json, urllib.request, urllib.error, sys, time

BASE = 'http://127.0.0.1:8778'
results = []
passed = 0
failed = 0

def test(name, method, path, data=None, timeout=15):
    global passed, failed
    url = f'{BASE}{path}'
    try:
        body = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header('Content-Type', 'application/json')
        r = urllib.request.urlopen(req, timeout=timeout)
        resp = json.loads(r.read())
        status = r.status
        if name.startswith('POST') and 'process' in name.lower():
            status_ok = status == 200 and resp.get('response', '') != ''
        else:
            status_ok = status == 200
        if status_ok:
            passed += 1
            results.append((name, 'PASS', resp))
        else:
            failed += 1
            results.append((name, f'FAIL (status={status})', resp))
    except urllib.error.HTTPError as e:
        failed += 1
        try:
            body = e.read().decode()
            results.append((name, f'FAIL (HTTP {e.code})', body[:200]))
        except:
            results.append((name, f'FAIL (HTTP {e.code})', ''))
    except Exception as e:
        failed += 1
        results.append((name, f'FAIL ({type(e).__name__}: {e})', ''))

print('=== MOON API Comprehensive Verification ===')
print(f'Base URL: {BASE}')
print()

# 1. Health
print('--- Health & Info ---')
test('1. GET /api/health', 'GET', '/api/health')

# 2. Agent profiles
print('--- Agent Profiles ---')
for agent in ['general', 'code', 'browser', 'planner', 'analyst', 'security', 'creative', 'devops', 'research', 'finance', 'health', 'media', 'tool']:
    test(f'GET /api/agents/{agent}', 'GET', f'/api/agents/{agent}')

# 3. Tools list
print('--- Tools ---')
test('GET /api/tools', 'GET', '/api/tools')

# 4. Memory
print('--- Memory ---')
test('GET /api/moon-agent/memory', 'GET', '/api/moon-agent/memory')
test('POST /api/moon-agent/memory (write)', 'POST', '/api/moon-agent/memory', {'key': 'verify_key', 'value': 'verify_val', 'session_id': 'verify'})
test('GET /api/moon-agent/memory (after write)', 'GET', '/api/moon-agent/memory')

# 5. Clear memory
print('--- Clear ---')
test('POST /api/moon-agent/clear', 'POST', '/api/moon-agent/clear')

# 6. Route query
print('--- Router ---')
test('GET /api/moon-agent/route?query=hello', 'GET', '/api/moon-agent/route?query=hello')

# 7. List agents (GET /api/moon-agent)
print('--- Agent List ---')
test('GET /api/moon-agent (list)', 'GET', '/api/moon-agent')

# 8. Process message — use a tool-based prompt so it doesn't hang on empty LLM
print('--- Process Message (tool-focused) ---')
test('POST /api/moon-agent (process)', 'POST', '/api/moon-agent', {
    'message': 'Use tool system_info to get system info',
    'agent': 'general',
    'session_id': 'verify_proc'
}, timeout=15)

# 9. Run specific tools
print('--- Tool Execution ---')
test('POST /api/tools/system_info', 'POST', '/api/tools/system_info', {})
test('POST /api/tools/time', 'POST', '/api/tools/time', {})

# 10. WebSocket — actual connect + echo test
print('--- WebSocket ---')
test('GET /api/moon-agent/ws_info', 'GET', '/api/moon-agent/ws_info')
try:
    import asyncio as _asyncio
    import websockets as _ws
    async def _ws_test():
        async with _ws.connect(f'{BASE.replace("http", "ws")}/api/ws') as ws:
            await ws.send(json.dumps({'type': 'test', 'message': 'hello'}))
            resp = await _asyncio.wait_for(ws.recv(), timeout=3)
            data = json.loads(resp)
            return data.get('type') == 'echo' and data.get('message') == 'hello'
    ws_ok = _asyncio.run(_ws_test())
    if ws_ok:
        passed += 1
        results.append(('WS /api/ws connect+echo', 'PASS', ''))
    else:
        failed += 1
        results.append(('WS /api/ws connect+echo', 'FAIL (echo mismatch)', ''))
except Exception as e:
    failed += 1
    results.append(('WS /api/ws connect+echo', f'FAIL ({type(e).__name__})', ''))

# Summary
print()
print('=== RESULTS ===')
for name, status, resp in results:
    icon = '\u2713' if status == 'PASS' else '\u2717'
    print(f'  {icon} {name}: {status}')
    if status != 'PASS' and resp:
        print(f'     Response: {str(resp)[:150]}')

print(f'\nTotal: {passed} passed, {failed} failed, {passed+failed} total')
