# MOON Superadvanced Capabilities — 5 new tools
# These are loaded by agent/engine.py via import and register calls
# Use lazy import of default_engine to avoid circular import

import asyncio
import re as _re
from collections import defaultdict as _dd

from agent.engine import _eng


async def _tool_research_pipeline(args: dict) -> dict:
    """Multi-source research: search → extract top results → LLM synthesis with citations."""
    topic = args.get("topic", "").strip()
    if not topic:
        return {"error": "topic is required"}
    max_results = int(args.get("max_results", 5))
    extract_top = int(args.get("extract_top", 3))
    report = {
        "topic": topic,
        "started_at": asyncio.get_event_loop().time(),
        "search_results": [],
        "extracted_content": [],
        "synthesized_report": "",
        "citations": [],
        "status": "in_progress",
    }
    try:
        sr = await _eng().run_tool("web_search", {"query": topic, "limit": max_results})
        results = sr.get("results", [])
        report["search_results"] = results
        report["citations"] = [r.get("url", "") for r in results if r.get("url")]
    except Exception as e:
        report["search_error"] = str(e)
    for r in (report["search_results"] or [])[:extract_top]:
        url = r.get("url", "")
        if url:
            try:
                ex = await _eng().run_tool("web_extract", {"url": url})
                report["extracted_content"].append({
                    "url": url,
                    "title": r.get("title", ""),
                    "excerpt": (ex.get("content") or "")[:800],
                })
            except Exception:
                pass
    if _eng()._llm is not None and report["extracted_content"]:
        try:
            ctx = "\n".join(f"[{i+1}] {e['title']}: {e['excerpt']}"
                           for i, e in enumerate(report["extracted_content"]))
            resp = await _eng()._llm.chat(
                message=(
                    f"Research topic: {topic}\n\n"
                    f"Source material:\n{ctx}\n\n"
                    "Write a concise research report (3-5 paragraphs) with a "
                    "'Key Findings' section and cite sources as [1], [2], etc. "
                    "Match citation numbers to the source list above."
                ),
                system="You are a research analyst. Be factual, cite sources by number.",
            )
            report["synthesized_report"] = (resp.get("content") or "").strip()
        except Exception as e:
            report["synthesize_error"] = str(e)
    else:
        report["synthesized_report"] = "LLM unavailable — raw search results attached."
    report["status"] = "complete"
    report["completed_at"] = asyncio.get_event_loop().time()
    report["total_sources"] = len(report["search_results"])
    return report


async def _tool_reasoning_chain(args: dict) -> dict:
    """Chain-of-thought reasoning: decompose → reason step-by-step → synthesize final answer."""
    problem = args.get("problem", "").strip()
    if not problem:
        return {"error": "problem is required"}
    trace: list[dict] = []
    if _eng()._llm is None:
        return {
            "problem": problem,
            "note": "LLM unavailable — cannot perform chain-of-thought reasoning",
            "trace": trace,
        }
    try:
        resp = await _eng()._llm.chat(
            message=(
                f"Problem: {problem}\n\n"
                "Break this into 3-5 concrete reasoning steps. List each step "
                "on its own line, no numbering, no intro text."
            ),
            system="You are a reasoning planner. Be concise.",
        )
        steps_text = (resp.get("content") or "").strip()
        steps = [s.strip() for s in steps_text.splitlines()
                 if s.strip() and len(s.strip()) > 3]
        if not steps:
            steps = [problem]
        trace.append({"step": 0, "phase": "decomposition", "output": steps_text[:500]})
        accumulated = ""
        for i, step in enumerate(steps[:5], 1):
            prompt = (
                f"Step {i}: {step}\n\n"
                f"Previous reasoning:\n{accumulated}\n\n"
                "Reason through this step."
            )
            resp = await _eng()._llm.chat(
                message=prompt,
                system="You are a step-by-step reasoner. Be direct.",
            )
            step_output = (resp.get("content") or "").strip()
            trace.append({
                "step": i,
                "phase": "reasoning",
                "step_prompt": step,
                "output": step_output[:500],
            })
            accumulated += f"\nStep {i}: {step_output}"
        resp = await _eng()._llm.chat(
            message=(
                f"Problem: {problem}\n\n"
                f"Full reasoning trace:\n{accumulated}\n\n"
                "Give the final, definitive answer based on the reasoning above. "
                "Be concise."
            ),
            system="You are a conclusion synthesizer.",
        )
        final = (resp.get("content") or "").strip()
        trace.append({"step": "final", "phase": "synthesis", "output": final[:500]})
        return {
            "problem": problem,
            "trace": trace,
            "final_answer": final,
            "step_count": len([t for t in trace if t.get("phase") == "reasoning"]),
        }
    except Exception as e:
        trace.append({"step": "error", "phase": "failed", "error": str(e)})
        return {"problem": problem, "trace": trace, "error": str(e)}


async def _tool_knowledge_graph(args: dict) -> dict:
    """Build and query an in-memory knowledge graph from MOON's memory.

    Extracts entities and relationships from memory entries, builds a graph,
    supports queries, stats, and BFS shortest-path between entities.
    """
    action = args.get("action", "query")
    query = args.get("query", "").strip().lower()
    limit = int(args.get("limit", 10))
    entities: dict[str, set[str]] = _dd(set)
    mentions: dict[str, int] = _dd(int)
    for m in _eng()._memory:
        data = m.get("data", {})
        text = str(data).lower()
        words = _re.findall(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", text)
        freq: dict[str, int] = _dd(int)
        for w in words:
            if len(w) >= 3 and not _re.match(
                r"^(the|and|for|with|from|that|this|was|were|are|is|has|have"
                r"|its|our|your|their|not|but|all|can|will|just|also|very|been"
                r"|some|into|over|such|only|other|new|more|these|those|than|then"
                r"|now|how|what|when|where|why|who|which|does|did|could|would"
                r"|should|may|might|shall|must|about|after|before|between|under"
                r"|again|once|here|there|each|every|both|few|most|no|nor|too"
                r"|don|today|monday|tuesday|wednesday|thursday|friday"
                r"|saturday|sunday|january|february|march|april|may|june|july"
                r"|august|september|october|november|december|am|pm|url|http"
                r"|https|www|com|org|net|io|pdf|txt|md|py|js|ts|html|css|json"
                r"|yaml|xml|sql|git|dev|log|tmp|bin|exe|dll|so|app|img|src|lib"
                r"|usr|home|etc|var|run|mnt|opt|root|sys|proc|boot|media|srv"
                r")$",
                w,
            ):
                freq[w] += 1
        top = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:8]
        entity_names = [w for w, _ in top if w]
        for e in entity_names:
            mentions[e] += 1
            entities[e].update(
                [w for w, _ in top if w != e]
            )
    if action == "query":
        matched = [e for e in entities if query in e] if query else list(entities.keys())[:limit]
        if not matched and query:
            matched = [e for e in entities if query in e or e in query]
        return {
            "query": query,
            "matched_entities": matched[:limit],
            "total_entities": len(entities),
            "entity_details": [
                {"name": e, "mentions": mentions[e], "related": list(entities[e])[:10]}
                for e in matched[:limit]
            ],
            "top_entities": sorted(
                mentions.items(), key=lambda x: x[1], reverse=True
            )[:10],
        }
    elif action == "stats":
        return {
            "total_entities": len(entities),
            "total_relationships": sum(len(v) for v in entities.values()) // 2,
            "top_entities": [
                {"name": e, "mentions": c}
                for e, c in sorted(mentions.items(), key=lambda x: x[1], reverse=True)[:15]
            ],
        }
    elif action == "path":
        start = args.get("start", "").lower()
        end = args.get("end", "").lower()
        if not start or not end or start not in entities or end not in entities:
            return {
                "error": "both start and end entities must exist in graph",
                "start": start,
                "end": end,
            }
        visited: set[str] = {start}
        queue: list[tuple[str, list[str]]] = [(start, [start])]
        while queue:
            node, path = queue.pop(0)
            if node == end:
                return {"path": path, "start": start, "end": end, "length": len(path) - 1}
            for neighbor in entities.get(node, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))
        return {"path": None, "start": start, "end": end, "connected": False}
    return {"error": f"unknown action: {action}"}


async def _tool_code_generator(args: dict) -> dict:
    """Generate executable code from a natural-language description via LLM, then run it."""
    description = args.get("description", "").strip()
    if not description:
        return {"error": "description is required"}
    if _eng()._llm is None:
        return {"error": "LLM unavailable for code generation"}
    try:
        resp = await _eng()._llm.chat(
            message=(
                f"Generate Python code that does the following:\n\n"
                f"{description}\n\n"
                "Return ONLY the code, no explanations, no markdown fences. "
                "Make it a complete, runnable script with a main block."
            ),
            system="You are a Python code generator. Output only runnable code.",
        )
        code = (resp.get("content") or "").strip()
        code = _re.sub(r"^```\w*\n?", "", code)
        code = _re.sub(r"\n?```$", "", code)
        result = {"generated_code": code, "language": "python", "executed": False}
        if code:
            try:
                exec_result = await _eng().run_tool(
                    "python_executor", {"code": code, "timeout": 30}
                )
                result["executed"] = True
                result["execution"] = {
                    "stdout": exec_result.get("stdout", ""),
                    "stderr": exec_result.get("stderr", ""),
                    "returncode": exec_result.get("returncode"),
                    "output": exec_result.get("output", ""),
                }
            except Exception as e:
                result["execution_error"] = str(e)
        return result
    except Exception as e:
        return {"error": f"code generation failed: {e}", "description": description}


async def _tool_auto_agent(args: dict) -> dict:
    """Auto-select the best agent and tool chain for a task, execute, synthesize."""
    task = args.get("task", "").strip()
    if not task:
        return {"error": "task is required"}
    task_lower = task.lower()
    # Score agents
    scores: dict[str, int] = {}
    for name, persona in _eng().personas.items():
        s = 0
        for kw in _re.findall(r"[a-z]+", persona.description.lower()):
            if kw in task_lower:
                s += 2
        if name.replace("_", " ") in task_lower or name in task_lower:
            s += 10
        scores[name] = s
    best_agent = max(scores, key=scores.get) if scores else "general"
    best_score = scores.get(best_agent, 0)
    # Tool selection by keyword
    tool_keywords: dict[str, list[str]] = {
        "web_search": ["search", "find", "research", "look up", "article", "information"],
        "web_extract": ["extract", "scrape", "fetch", "url", "website"],
        "file_read": ["read file", "cat", "file content"],
        "file_write": ["write file", "save", "create file"],
        "shell": ["shell", "command", "exec", "run", "bash"],
        "python_executor": ["python", "code", "script", "compute"],
        "system_info": ["system", "info", "status", "health", "os"],
        "memory_read": ["memory", "remember", "recall", "history"],
        "memory_write": ["remember this", "store", "learn"],
        "network_scan": ["network", "scan", "port", "host"],
        "dns_lookup": ["dns", "domain", "resolve", "ip"],
        "git_ops": ["git", "commit", "log", "repo"],
        "health_check": ["health", "status", "uptime"],
        "service_control": ["restart", "start service", "stop service"],
        "security_tools": ["security", "vulnerability", "audit"],
        "data_export": ["export", "json", "yaml", "csv", "data"],
        "encryption": ["encrypt", "decrypt", "crypto"],
        "qr_generator": ["qr", "code"],
        "log_read": ["log", "logs", "tail"],
        "template_render": ["template", "render"],
        "data_viz": ["chart", "graph", "plot", "visualize"],
        "rest_api_framework": ["api", "rest", "endpoint"],
        "http_request": ["http", "request", "curl", "api call"],
        "email_sender": ["email", "send mail"],
        "archive": ["archive", "zip", "tar"],
        "ascii_art": ["ascii", "art", "draw", "banner"],
        "voice_speak": ["speak", "voice", "say", "TTS"],
        "docker": ["docker", "container"],
        "ssh_client": ["ssh", "remote"],
        "threat_intel": ["threat", "ioc"],
        "cve_search": ["cve", "vulnerability", "exploit"],
        "port_scanner": ["port scan", "ports"],
        "packet_capture": ["packet", "capture", "sniff"],
        "research_pipeline": ["research", "investigate", "deep dive"],
        "reasoning_chain": ["reason", "chain of thought", "step by step"],
        "knowledge_graph": ["knowledge graph", "graph", "entities"],
        "code_generator": ["generate code", "write code", "code gen"],
        "auto_agent": ["auto", "orchestrate", "dispatch"],
    }
    seen: set[str] = set()
    tool_chain: list[str] = []
    for tool_name, kws in tool_keywords.items():
        if any(kw in task_lower for kw in kws) and tool_name not in seen:
            tool_chain.append(tool_name)
            seen.add(tool_name)
    if not tool_chain:
        tool_chain = ["web_search", "system_info"]
    results: list[dict] = []
    context_text = ""
    for tn in tool_chain[:6]:
        try:
            tool_args = _auto_agent_build_args(tn, task, context_text)
            r = await _eng().run_tool(tn, tool_args)
            results.append({"tool": tn, "status": "ok", "preview": _result_preview(r)})
            context_text = _result_preview(r)
        except Exception as e:
            results.append({"tool": tn, "status": "error", "error": str(e)[:200]})
    final_answer = ""
    if _eng()._llm is not None:
        try:
            synthesis_prompt = (
                f"Task: {task}\n\n"
                "Tool results:\n"
                + "\n".join(
                    f"[{r['tool']}] {r.get('preview', r.get('error', ''))}"
                    for r in results
                )
                + "\n\nSynthesize a concise final answer."
            )
            resp = await _eng()._llm.chat(
                message=synthesis_prompt,
                system="You are a result synthesizer.",
            )
            final_answer = (resp.get("content") or "").strip()
        except Exception:
            pass
    return {
        "task": task,
        "selected_agent": best_agent,
        "agent_confidence": best_score,
        "tool_chain": tool_chain,
        "tool_results": results,
        "tools_run": len(tool_chain),
        "tools_succeeded": sum(1 for r in results if r["status"] == "ok"),
        "final_synthesis": final_answer,
    }


def _auto_agent_build_args(tool_name: str, task: str, ctx: str) -> dict:
    """Build appropriate args for a tool given the task and prior context."""
    tl = task.lower()
    if tool_name == "web_search":
        return {"query": task, "limit": 5}
    if tool_name == "web_extract":
        urls = _re.findall(r"https?://[^\s,;]+", task)
        return {"url": urls[0] if urls else "https://example.com"}
    if tool_name == "file_read":
        paths = _re.findall(r"(/[^\s,;'\"\"]+)", task)
        return {"path": paths[0] if paths else "/home/meow/Projects/MOON/README.md"}
    if tool_name == "file_write":
        paths = _re.findall(r"(/[^\s,;'\"\"]+)", task)
        return {"path": paths[0] if paths else "/tmp/moon_out.txt", "content": ctx[:5000]}
    if tool_name == "shell":
        return {"command": task[:500]}
    if tool_name == "python_executor":
        return {"code": task[:2000], "timeout": 30}
    if tool_name == "dns_lookup":
        domains = _re.findall(r"[a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}", task)
        return {"domain": domains[0] if domains else "example.com"}
    if tool_name == "network_scan":
        return {"targets": ["127.0.0.1"], "ports": [22, 80, 443, 8777, 8778]}
    if tool_name == "git_ops":
        return {"subcommand": "log", "directory": "/home/meow/Projects/MOON", "limit": 5}
    if tool_name == "service_control":
        return {"action": "status", "service": "moon.service"}
    if tool_name == "memory_read":
        return {"session_id": "", "limit": 10}
    if tool_name == "memory_write":
        return {"data": {"task": task[:500]}}
    if tool_name == "security_tools":
        return {"technique": "info"}
    if tool_name in ("data_export", "yaml_ops"):
        return {"data": {"task": task[:500]}, "format": "json" if tool_name == "data_export" else "yaml"}
    if tool_name == "encryption":
        return {"action": "generate_key"}
    if tool_name == "qr_generator":
        return {"data": task[:200], "size": 4}
    if tool_name == "log_read":
        return {"path": "/var/log/syslog", "lines": 50}
    if tool_name == "template_render":
        return {"template": task[:500], "variables": {}}
    if tool_name == "data_viz":
        return {"data": [1, 2, 3, 4, 5], "chart_type": "bar", "title": task[:50]}
    if tool_name == "rest_api_framework":
        return {"endpoints": [{"path": "/task", "method": "POST"}], "port": 8080}
    if tool_name == "http_request":
        urls = _re.findall(r"https?://[^\s,;]+", task)
        return {"url": urls[0] if urls else "https://httpbin.org/get"}
    if tool_name == "email_sender":
        return {"to": "user@example.com", "subject": task[:100], "body": ctx[:1000]}
    if tool_name == "archive":
        return {"action": "create", "source": "/home/meow/Projects/MOON", "output": "/tmp/moon.tar.gz", "format": "tar.gz"}
    if tool_name == "ascii_art":
        return {"text": task[:100], "font": "standard"}
    if tool_name == "voice_speak":
        return {"text": task[:500], "voice": "default"}
    if tool_name == "research_pipeline":
        return {"topic": task[:200], "max_results": 5, "extract_top": 3}
    if tool_name == "reasoning_chain":
        return {"problem": task[:1000]}
    if tool_name == "knowledge_graph":
        return {"action": "query", "query": task[:200], "limit": 10}
    if tool_name == "code_generator":
        return {"description": task[:1000]}
    if tool_name == "auto_agent":
        return {"task": task[:1000]}
    return {}


def _result_preview(result: dict) -> str:
    """Extract a human-readable preview from a tool result dict."""
    if not isinstance(result, dict):
        return str(result)[:200]
    for key in ("content", "stdout", "output", "summary", "answer",
                "synthesized_report", "final_answer", "message"):
        val = result.get(key)
        if val and isinstance(val, str) and val.strip():
            return val.strip()[:300]
    for key in ("results", "items", "data", "entries", "matches", "findings"):
        val = result.get(key)
        if val and isinstance(val, list) and val:
            first = val[0]
            return (first if isinstance(first, str) else str(first))[:300]
    return str(result)[:300]
