"""Verify MOON API v1.2.0 — all 10 endpoints live on :8778.

Required deliverable from Compact §19/20:
  Compile, deploy, test, document.
"""

import asyncio
import json
import sys
import time
import urllib.request
from urllib.error import URLError

BASE = "http://127.0.0.1:8778"
TIMEOUT = 20


def get(url, data=None):
    """GET or POST to BASE+url, return decoded JSON."""
    full = BASE + url
    if data is not None:
        body = json.dumps(data).encode()
        req = urllib.request.Request(full, data=body, headers={"Content-Type": "application/json"})
    else:
        req = urllib.request.Request(full)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


def run_tests():
    results = []
    start = time.time()
    total = 10

    def check(name, fn):
        try:
            val = fn()
            results.append((name, "OK", val))
        except Exception as e:
            results.append((name, "FAIL", str(e)[:140]))

    # 1. health
    check("/api/health", lambda: get("/api/health"))

    # 2. tools list (count only)
    check("/api/tools (count)", lambda: get("/api/tools").get("count"))

    # 3. tools/system_info
    check("/api/tools/system_info", lambda: get("/api/tools/system_info", {}))

    # 4. tools/network_scan (tiny range to be fast)
    check("/api/tools/network_scan",
          lambda: get("/api/tools/network_scan", {"network": "127.0.0.1/32", "ports": "8778", "workers": 2}))

    # 5. agents list (count only)
    check("/api/agents (count)", lambda: get("/api/agents").get("count"))

    # 6. single agent GET
    check("/api/agents/general",
          lambda: get("/api/agents/general"))

    # 7. POST /api/moon-agent (message)
    check("/api/moon-agent (POST)",
          lambda: get("/api/moon-agent", {"message": "primary role in 1 sentence."}))

    # 8. /api/moon-agent/agents (count)
    check("/api/moon-agent/agents (count)",
          lambda: get("/api/moon-agent/agents").get("count"))

    # 9. /api/moon-agent/agents/general (POST)
    check("/api/moon-agent/agents/general (POST)",
          lambda: get("/api/moon-agent/agents/general", {"message": "role in 1 sentence."}))

    # 10. /api/moon-agent/clear
    check("/api/moon-agent/clear",
          lambda: get("/api/moon-agent/clear"))

    elapsed = time.time() - start
    ok = sum(1 for _, s, _ in results if s == "OK")

    print()
    print("=================================================")
    print(f"  MOON API VERIFICATION  —  {BASE}")
    print("=================================================")
    print(f"  Time: {elapsed:.1f}s   |   Passed: {ok}/{total}")
    print("=================================================")
    for i, (name, status, detail) in enumerate(results, 1):
        mark = "OK" if status == "OK" else "FAIL"
        print(f"  {i:2d}. [{mark}] {name}")
        if status == "OK" and detail is not None:
            if isinstance(detail, dict):
                if "error" in detail:
                    print(f"       ERROR: {detail['error']}")
                elif "response" in detail:
                    print(f"       agent={detail.get('agent','?')} :: {detail['response'][:80]}")
                elif "result" in detail and isinstance(detail["result"], dict):
                    r = detail["result"]
                    for k in ("live_hosts", "open_ports", "scan_duration_s"):
                        if k in r:
                            print(f"       {k}={r[k]}")
                elif "status" in detail:
                    print(f"       {detail['status']}")
                elif "tool" in detail:
                    print(f"       tool={detail['tool']}")
                elif "count" in detail:
                    print(f"       count={detail['count']}")
                else:
                    keys = list(detail.keys())
                    print(f"       keys={keys}")
                    print(f"       {json.dumps(detail, default=str)[:120]}")
            elif isinstance(detail, str) and detail:
                print(f"       {detail[:100]}")
        elif status == "FAIL":
            print(f"       {detail}")
    print("=================================================")

    if ok == total:
        print("  ALL ENDPOINTS VERIFIED LIVE")
        print("  v1.2.0 — FULL INTEGRATION COMPLETE")
        return 0
    else:
        print(f"  {total - ok} ENDPOINT(S) FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(run_tests())
