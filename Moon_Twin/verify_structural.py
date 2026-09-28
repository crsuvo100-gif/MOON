#!/usr/bin/env python3
"""
MOON Project Structural Integrity Verifier
===================================================
Scans the full MOON project tree, maps every folder/subfolder,
validates that all wiring between modules is one-to-one consistent,
and confirms the project compiles and boots as a professional AI assistant agent.
"""

from __future__ import annotations
import ast
import importlib
import inspect
import json
import os
import pkgutil
import sys
import traceback
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path("/home/meow/Projects/MOON")
MOON_TWIN = PROJECT_ROOT / "Moon_Twin"
APP_DIR = PROJECT_ROOT / "app"
TERMINAL_MOON = PROJECT_ROOT / "terminal_moon"

class Color:
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    RED = "\033[31m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

def c(color: str, text: str) -> str:
    return f"{color}{text}{Color.RESET}"

def main() -> None:
    print(c(Color.BOLD, "=" * 78))
    print(c(Color.BOLD, "  MOON PROJECT STRUCTURAL INTEGRITY VERIFIER"))
    print(c(Color.BOLD, "  Full tree scan · wiring map · compile check · boot verification"))
    print(c(Color.BOLD, "=" * 78))
    print()

    results: Dict[str, Any] = {}

    # ── Phase 1: Full directory tree ──────────────────────────────────────
    print(c(Color.CYAN, "[PHASE 1] Full directory tree scan"))
    print("-" * 70)
    tree = scan_tree(PROJECT_ROOT)
    results["tree"] = tree
    print_tree(tree, PROJECT_ROOT)
    print()

    # ── Phase 2: File inventory ────────────────────────────────────────────
    print(c(Color.CYAN, "[PHASE 2] Complete file inventory"))
    print("-" * 70)
    files = scan_files(PROJECT_ROOT)
    results["file_count"] = len(files)
    results["files"] = files
    print(f"Total files: {len(files)}")
    for f in sorted(files):
        rel = f.relative_to(PROJECT_ROOT)
        print(f"  {rel}")
    print()

    # ── Phase 3: Python module discovery ──────────────────────────────────
    print(c(Color.CYAN, "[PHASE 3] Python module discovery & import graph"))
    print("-" * 70)
    modules = discover_python_modules(PROJECT_ROOT)
    results["modules"] = [str(m.relative_to(PROJECT_ROOT)) for m in modules]
    print(f"Python modules found: {len(modules)}")
    for m in sorted(modules):
        rel = m.relative_to(PROJECT_ROOT)
        print(f"  {rel}")
    print()

    # ── Phase 4: Wiring map — cross-reference imports ─────────────────────
    print(c(Color.CYAN, "[PHASE 4] Wiring map — import cross-references"))
    print("-" * 70)
    wiring = build_wiring_map(modules, PROJECT_ROOT)
    results["wiring"] = wiring
    print_wiring_map(wiring, modules)
    print()

    # ── Phase 5: Structural consistency check ─────────────────────────────
    print(c(Color.CYAN, "[PHASE 5] Structural consistency check"))
    print("-" * 70)
    consistency = check_consistency(wiring, modules, PROJECT_ROOT)
    results["consistency"] = consistency
    print_consistency(consistency)
    print()

    # ── Phase 6: Moon_Twin + app wiring ───────────────────────────────────
    print(c(Color.CYAN, "[PHASE 6] Moon_Twin ↔ app ↔ terminal_moon cross-wiring"))
    print("-" * 70)
    cross = cross_wire_check()
    results["cross_wire"] = cross
    print_cross_wire(cross)
    print()

    # ── Phase 7: AST import analysis per module ───────────────────────────
    print(c(Color.CYAN, "[PHASE 7] AST-level import dependency graph"))
    print("-" * 70)
    ast_graph = ast_import_analysis(modules, PROJECT_ROOT)
    results["ast_graph"] = ast_graph
    print_ast_graph(ast_graph)
    print()

    # ── Phase 8: Functional verification ──────────────────────────────────
    print(c(Color.CYAN, "[PHASE 8] Functional verification (live service)"))
    print("-" * 70)
    func = functional_verification()
    results["functional"] = func
    print_functional(func)
    print()

    # ── Phase 9: Compile check ────────────────────────────────────────────
    print(c(Color.CYAN, "[PHASE 9] Python compile check (all .py files)"))
    print("-" * 70)
    compile_results = compile_check(PROJECT_ROOT)
    results["compile"] = compile_results
    print_compile(compile_results)
    print()

    # ── Phase 10: Full summary ────────────────────────────────────────────
    print(c(Color.BOLD, "=" * 78))
    print(c(Color.BOLD, "  FINAL VERIFICATION SUMMARY"))
    print(c(Color.BOLD, "=" * 78))
    summary = build_summary(results)
    print(summary)
    print()

    # Write report
    report_path = PROJECT_ROOT / "MOON_STRUCTURAL_VERIFICATION_REPORT.json"
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(c(Color.GREEN, f"[REPORT] Written to: {report_path}"))
    print()

    # Return exit code
    all_ok = all([
        consistency["duplicates"] == 0,
        consistency["missing_def_internal"] == 0,
        compile_results["failed"] == 0,
        func["healthy"],
        func["agent_count"] > 0,
    ])
    if all_ok:
        print(c(Color.GREEN, "[PASS] MOON project is fully wired, compiled, and functional."))
        sys.exit(0)
    else:
        print(c(Color.RED, "[WARN] Some checks flagged — review report for details."))
        sys.exit(1)


# ── Phase 1: Tree scan ────────────────────────────────────────────────────

def scan_tree(root: Path) -> Dict[str, Any]:
    """Return nested dict representing directory tree."""
    tree: Dict[str, Any] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirpath = Path(dirpath)
        if any(skip in str(dirpath) for skip in [".git", "__pycache__", ".venv", "node_modules"]):
            continue
        rel = dirpath.relative_to(root)
        parts = list(rel.parts)
        current = tree
        for part in parts:
            if part not in current:
                current[part] = {}
            current = current[part]
        current["_files"] = sorted(f for f in filenames if not f.startswith("."))
    return tree


def print_tree(tree: Dict, root: Path, indent: int = 0) -> None:
    prefix = "  " * indent
    for name, subtree in sorted(tree.items()):
        if name == "_files":
            continue
        full = root / "/".join(_path_to_parts(tree, name))
        is_dir = full.is_dir()
        marker = "📁" if is_dir else "📄"
        print(f"{prefix}{marker} {name}/")
        if isinstance(subtree, dict):
            print_tree(subtree, root / name, indent + 1)


def _path_to_parts(tree: Dict, name: str) -> list:
    """Navigate back — not needed for printing, we pass root down."""
    return [name]


# ── Phase 2: File scan ────────────────────────────────────────────────────

def scan_files(root: Path) -> List[Path]:
    files: List[Path] = []
    for dirpath, _, filenames in os.walk(root):
        dirpath = Path(dirpath)
        if any(skip in str(dirpath) for skip in [".git", "__pycache__", ".venv", "node_modules"]):
            continue
        for fn in filenames:
            if fn.startswith("."):
                continue
            files.append(dirpath / fn)
    return files


# ── Phase 3: Module discovery ─────────────────────────────────────────────

def discover_python_modules(root: Path) -> List[Path]:
    modules: List[Path] = []
    for dirpath, _, filenames in os.walk(root):
        dirpath = Path(dirpath)
        if any(skip in str(dirpath) for skip in [".git", "__pycache__", ".venv", "node_modules"]):
            continue
        for fn in filenames:
            if fn.endswith(".py") and not fn.startswith("."):
                modules.append(dirpath / fn)
    return modules


# ── Phase 4: Wiring map ───────────────────────────────────────────────────

def read_imports(py_path: Path) -> List[str]:
    """Extract top-level imported module names from a Python file via AST."""
    try:
        source = py_path.read_text()
        tree = ast.parse(source, filename=str(py_path))
        imports: List[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module.split(".")[0])
        return imports
    except Exception:
        return []


def resolve_import_target(import_name: str, modules: List[Path], root: Path) -> Optional[str]:
    """Try to resolve an import to a local module path."""
    # Direct matching: app.XX, moon_twins, etc.
    for mod in modules:
        rel = mod.relative_to(root)
        parts = list(rel.parts)
        if parts[-1].startswith("__init__"):
            parts = parts[:-1]
        else:
            parts[-1] = parts[-1][:-3]  # strip .py
        if parts and parts[0] == import_name:
            return str(rel).replace("/", ".")
        # Also match moon_twins style against Moon_Twin
        if import_name == "Moon_Twin" or import_name == "moon_twin":
            if "Moon_Twin" in str(mod) or "moon_twin" in str(mod).lower():
                return "Moon_Twin"
        # terminal_moon
        if import_name == "terminal_moon":
            if "terminal_moon" in str(mod):
                return "terminal_moon"
    return None


def build_wiring_map(modules: List[Path], root: Path) -> Dict[str, List[Tuple[str, Optional[str]]]]:
    """Map each module → list of (import_name, resolved_local_path or None)."""
    wiring: Dict[str, List[Tuple[str, Optional[str]]]] = {}
    for mod in modules:
        key = str(mod.relative_to(root))
        imports = read_imports(mod)
        resolved = []
        for imp in imports:
            target = resolve_import_target(imp, modules, root)
            resolved.append((imp, target))
        wiring[key] = resolved
    return wiring


def print_wiring_map(wiring: Dict, modules: List[Path]) -> None:
    for mod, imps in sorted(wiring.items()):
        resolved_count = sum(1 for _, t in imps if t is not None)
        external = [n for n, t in imps if t is None and n not in ("os", "sys", "json", "typing", "pathlib",
                                                               "re", "datetime", "collections", "functools",
                                                               "asyncio", "logging", "hashlib", "base64",
                                                               "io", "contextlib", "dataclasses", "enum",
                                                               "abc", "threading", "time", "math", "copy",
                                                               "itertools", "operator", "ast", "traceback",
                                                               "warnings", "subprocess", "socket", "struct",
                                                               "urllib", "http", "email", "csv", "sqlite3",
                                                               "venv", "unittest", "pytest", "click", "rich",
                                                               "toml", "yaml", "pickle", "textwrap", "shutil",
                                                               "glob", "tempfile", "random", "string", "decimal",
                                                               "fractions", "typing_extensions", "grpclib",
                                                               "grpc", "protobuf", "aiohttp", "websockets",
                                                               "requests", "httpx", "fastapi", "uvicorn",
                                                               "starlette", "pydantic", "sqlalchemy", "redis",
                                                               "numpy", "pandas", "matplotlib", "PIL", "cv2",
                                                               "scipy", "sklearn", "torch", "tensorflow",
                                                               "jax", "transformers", "sentencepiece", "tokenizers",
                                                               "bitsandbytes", "peft", "accelerate", "deepspeed")]
        internal = [(n, t) for n, t in imps if t is not None]
        print(f"  {mod}: {len(imps)} imports ({resolved_count} local, {len(external)} external)")
        for name, target in internal[:15]:
            print(f"    → {name} → {target}")
        if len(internal) > 15:
            print(f"    ... +{len(internal)-15} more local")
        if external:
            print(f"    (ext) {', '.join(sorted(set(external))[:8])}")
            if len(set(external)) > 8:
                print(f"    ... +{len(set(external))-8} more external")


# ── Phase 5: Consistency ──────────────────────────────────────────────────

def check_consistency(wiring: Dict, modules: List[Path], root: Path) -> Dict[str, Any]:
    """Check for duplicate definitions and missing internal imports."""
    # Build index: module_path → list of defined names (top-level classes/functions)
    definitions: Dict[str, Set[str]] = {}
    for mod in modules:
        try:
            source = mod.read_text()
            tree = ast.parse(source, filename=str(mod))
            names: Set[str] = set()
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    names.add(node.name)
            rel = str(mod.relative_to(root))
            definitions[rel] = names
        except Exception:
            definitions[str(mod.relative_to(root))] = set()

    # Detect duplicates: same name defined in multiple modules (not __init__ re-export)
    name_to_modules: Dict[str, List[str]] = defaultdict(list)
    for mod_path, names in definitions.items():
        for name in names:
            name_to_modules[name].append(mod_path)
    duplicates = []
    for name, mods in name_to_modules.items():
        if len(mods) > 1:
            # Filter out common __init__ re-exports
            non_init = [m for m in mods if not m.endswith("/__init__.py") and "__init__" not in m]
            if len(non_init) > 1 or (len(non_init) == 1 and len(mods) > 1):
                duplicates.append((name, mods))

    # Missing internal: imports that reference local modules that don't exist
    missing: Dict[str, List[str]] = {}
    all_module_paths = set(str(m.relative_to(root)) for m in modules)
    for mod, imps in wiring.items():
        for name, target in imps:
            if target is None and not _is_standard_library(name):
                # Check if any module starts with this name
                found = any(mp.split("/")[0] == name or mp.split("/")[0] == name.replace("_", "")
                           for mp in all_module_paths)
                if not found:
                    if mod not in missing:
                        missing[mod] = []
                    missing[mod].append(name)

    return {
        "total_modules": len(modules),
        "total_definitions": sum(len(v) for v in definitions.values()),
        "duplicate_definitions": duplicates,
        "duplicates_count": len(duplicates),
        "missing_internal_imports": missing,
        "missing_count": sum(len(v) for v in missing.values()),
    }


def _is_standard_library(name: str) -> bool:
    stdlibs = {
        "os", "sys", "json", "typing", "pathlib", "re", "datetime", "collections",
        "functools", "asyncio", "logging", "hashlib", "base64", "io", "contextlib",
        "dataclasses", "enum", "abc", "threading", "time", "math", "copy", "itertools",
        "operator", "ast", "traceback", "warnings", "subprocess", "socket", "struct",
        "urllib", "http", "email", "csv", "sqlite3", "unittest", "typing_extensions",
        "grpclib", "grpc", "protobuf", "pickle", "textwrap", "shutil", "glob", "tempfile",
        "random", "string", "decimal", "fractions", "venv", "which",
    }
    return name in stdlibs


def print_consistency(consistency: Dict) -> None:
    print(f"  Modules scanned: {consistency['total_modules']}")
    print(f"  Total definitions: {consistency['total_definitions']}")
    print(f"  Duplicate definitions: {consistency['duplicates_count']}")
    if consistency["duplicate_definitions"]:
        for name, mods in consistency["duplicate_definitions"][:10]:
            print(f"    ⚠ {name} defined in: {', '.join(mods)}")
        if len(consistency["duplicate_definitions"]) > 10:
            print(f"    ... +{len(consistency['duplicate_definitions'])-10} more")
    print(f"  Missing internal imports: {consistency['missing_count']}")
    if consistency["missing_internal_imports"]:
        for mod, imps in list(consistency["missing_internal_imports"].items())[:10]:
            print(f"    ⚠ {mod}: {', '.join(imps)}")
        if len(consistency["missing_internal_imports"]) > 10:
            print(f"    ... +{len(consistency['missing_internal_imports'])-10} more modules")


# ── Phase 6: Cross-wiring ─────────────────────────────────────────────────

def cross_wire_check() -> Dict[str, Any]:
    """Check wiring between Moon_Twin, app/, and terminal_moon."""
    result: Dict[str, Any] = {}

    # Moon_Twin imports from app
    mt_dir = MOON_TWIN / "agent"
    mt_imports: Set[str] = set()
    for py in mt_dir.glob("*.py"):
        try:
            tree = ast.parse(py.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    mod = node.module
                    if mod.startswith("app.") or mod == "app":
                        mt_imports.add(mod)
        except Exception:
            pass
    result["moon_twin_imports_app"] = sorted(mt_imports)

    # app imports from Moon_Twin
    app_imports_mt: Set[str] = set()
    for py in APP_DIR.glob("**/*.py"):
        try:
            tree = ast.parse(py.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    mod = node.module
                    if mod.startswith("Moon_Twin") or mod == "Moon_Twin" or "moon_twin" in mod.lower():
                        app_imports_mt.add(mod)
        except Exception:
            pass
    result["app_imports_moon_twin"] = sorted(app_imports_mt)

    # terminal_moon imports from app
    tm_dir = TERMINAL_MOON / "app"
    tm_imports_app: Set[str] = set()
    for py in tm_dir.glob("**/*.py"):
        try:
            tree = ast.parse(py.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    mod = node.module
                    if mod.startswith("app.") or mod == "app":
                        tm_imports_app.add(mod)
        except Exception:
            pass
    result["terminal_moon_imports_app"] = sorted(tm_imports_app)

    # app imports from terminal_moon
    app_imports_tm: Set[str] = set()
    for py in APP_DIR.glob("**/*.py"):
        try:
            tree = ast.parse(py.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    mod = node.module
                    if "terminal_moon" in mod:
                        app_imports_tm.add(mod)
        except Exception:
            pass
    result["app_imports_terminal_moon"] = sorted(app_imports_tm)

    # Duplicates between Moon_Twin and terminal_moon
    mt_files: Set[str] = set()
    tm_files: Set[str] = set()
    for py in MOON_TWIN.glob("**/*.py"):
        mt_files.add(str(py.relative_to(PROJECT_ROOT)))
    for py in TERMINAL_MOON.glob("**/*.py"):
        tm_files.add(str(py.relative_to(PROJECT_ROOT)))
    common_structure = mt_files & tm_files
    result["shared_file_paths"] = sorted(common_structure)

    return result


def print_cross_wire(cross: Dict) -> None:
    print(f"  Moon_Twin → app imports: {len(cross['moon_twin_imports_app'])}")
    for imp in cross["moon_twin_imports_app"]:
        print(f"    → {imp}")
    print(f"  app → Moon_Twin imports: {len(cross['app_imports_moon_twin'])}")
    for imp in cross["app_imports_moon_twin"]:
        print(f"    → {imp}")
    print(f"  terminal_moon → app imports: {len(cross['terminal_moon_imports_app'])}")
    for imp in cross["terminal_moon_imports_app"]:
        print(f"    → {imp}")
    print(f"  app → terminal_moon imports: {len(cross['app_imports_terminal_moon'])}")
    for imp in cross["app_imports_terminal_moon"]:
        print(f"    → {imp}")
    print(f"  Shared file paths (Moon_Twin ∩ terminal_moon): {len(cross['shared_file_paths'])}")
    for fp in cross["shared_file_paths"]:
        print(f"    {fp}")


# ── Phase 7: AST graph ────────────────────────────────────────────────────

def ast_import_analysis(modules: List[Path], root: Path) -> Dict[str, List[str]]:
    """Return per-module list of all imports (AST-extracted)."""
    graph: Dict[str, List[str]] = {}
    for mod in modules:
        key = str(mod.relative_to(root))
        graph[key] = read_imports(mod)
    return graph


def print_ast_graph(graph: Dict) -> None:
    for mod, imps in sorted(graph.items()):
        if imps:
            print(f"  {mod}: imports {', '.join(sorted(set(imps)))}")


# ── Phase 8: Functional ───────────────────────────────────────────────────

def functional_verification() -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    try:
        import requests
        r = requests.get("http://127.0.0.1:8778/api/health", timeout=5)
        result["healthy"] = r.status_code == 200
        result["health_response"] = r.json() if r.status_code == 200 else {"error": r.status_code}
        result["health_status_code"] = r.status_code
    except Exception as e:
        result["healthy"] = False
        result["error"] = str(e)

    try:
        import requests
        r = requests.get("http://127.0.0.1:8778/api/moon-agent", timeout=5)
        result["agent_list_ok"] = r.status_code == 200
        if r.status_code == 200:
            data = r.json()
            result["agent_count"] = len(data.get("agents", []))
            result["agents"] = [a.get("id", "") for a in data.get("agents", [])]
        else:
            result["agent_count"] = 0
    except Exception as e:
        result["agent_list_ok"] = False
        result["agent_error"] = str(e)
        result["agent_count"] = 0

    return result


def print_functional(func: Dict) -> None:
    if func.get("healthy"):
        print(f"  Health endpoint: OK")
        print(f"  Response: {func.get('health_response', {})}")
    else:
        print(f"  Health endpoint: FAILED — {func.get('error', 'unknown')}")
    if func.get("agent_list_ok"):
        print(f"  Agent list: {func.get('agent_count', 0)} agents")
        for a in func.get("agents", []):
            print(f"    → {a}")
    else:
        print(f"  Agent list: FAILED — {func.get('agent_error', 'unknown')}")


# ── Phase 9: Compile ──────────────────────────────────────────────────────

def compile_check(root: Path) -> Dict[str, Any]:
    failed: List[str] = []
    checked: List[str] = []
    for py in root.rglob("*.py"):
        if any(skip in str(py) for skip in [".git", "__pycache__", ".venv", "node_modules"]):
            continue
        try:
            py.read_text()
            compile(py.read_text(), str(py), "exec")
            checked.append(str(py.relative_to(root)))
        except Exception as e:
            failed.append(f"{py.relative_to(root)}: {e}")
    return {"checked": checked, "failed": failed, "total": len(checked), "fail_count": len(failed)}


def print_compile(results: Dict) -> None:
    print(f"  Files checked: {results['total']}")
    print(f"  Compile failures: {results['fail_count']}")
    if results["failed"]:
        for f in results["failed"]:
            print(f"    ✗ {f}")
    else:
        print(f"  All {results['total']} Python files compile cleanly.")


# ── Summary ────────────────────────────────────────────────────────────────

def build_summary(results: Dict) -> str:
    lines = []
    lines.append(f"  Tree: {len(results.get('tree', {}))} top-level directories")
    lines.append(f"  Files: {results.get('file_count', 0)} total")
    lines.append(f"  Python modules: {len(results.get('modules', []))}")
    lines.append(f"  Duplicate definitions: {results.get('consistency', {}).get('duplicates_count', -1)}")
    lines.append(f"  Missing internal imports: {results.get('consistency', {}).get('missing_count', -1)}")
    compile_r = results.get("compile", {})
    lines.append(f"  Compile check: {compile_r.get('total', 0)} files, {compile_r.get('fail_count', 0)} failures")
    func_r = results.get("functional", {})
    lines.append(f"  Service health: {'HEALTHY' if func_r.get('healthy') else 'UNHEALTHY'}")
    lines.append(f"  Agent count: {func_r.get('agent_count', 0)}")
    lines.append(f"  Moon_Twin→app imports: {len(results.get('cross_wire', {}).get('moon_twin_imports_app', []))}")
    lines.append(f"  app→Moon_Twin imports: {len(results.get('cross_wire', {}).get('app_imports_moon_twin', []))}")
    lines.append(f"  terminal_moon→app imports: {len(results.get('cross_wire', {}).get('terminal_moon_imports_app', []))}")
    lines.append(f"  app→terminal_moon imports: {len(results.get('cross_wire', {}).get('app_imports_terminal_moon', []))}")
    lines.append(f"  Shared paths (MT∩TM): {len(results.get('cross_wire', {}).get('shared_file_paths', []))}")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
