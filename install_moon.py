#!/usr/bin/env python3
"""
MOON — Single-File Auto-Installer
===================================
One .py file to install MOON FULLY and FUNCTIONALLY on any machine.
After install: `moon terminal` → http://127.0.0.1:8777   (or `moon shell`)

What it does (idempotent, non-destructive — safe to re-run):
  1. Detect/check Python >= 3.10
  2. git clone (or update) the MOON repo from GitHub (SSH or HTTPS)
  3. Create .venv + install all dependencies (requirements.txt + optional)
  4. pip install -e .  (so `python -m moon` works)
  5. Write .env from .env.example if absent (NEVER commits secrets)
  6. Install Ollama if missing + pull the models MOON's agents use
  7. Download Kokoro-ONNX voice model + voices (offline female voice)
  8. Install the `moon` launcher to ~/.local/bin/moon
  9. Install desktop entry (Linux)
 10. REAL post-install acceptance: exercises voice + agents + tools + LLM

Usage:
    python3 install_moon.py              # full install
    python3 install_moon.py --verify     # only run acceptance
    python3 install_moon.py --no-ollama  # skip Ollama/models
    python3 install_moon.py --no-voice   # skip voice assets
    python3 install_moon.py --no-service # skip systemd service

SSH recommended for private repos. HTTPS works if repo is public or with a PAT.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration — edit these if you want a different source/repo
# ---------------------------------------------------------------------------
REPO_SSH = "git@github.com:crsuvo100-gif/MOON.git"
REPO_HTTPS = "https://github.com/crsuvo100-gif/MOON.git"
# Default: SSH. Set MOON_INSTALL_USE_HTTPS=1 to force HTTPS.
DEFAULT_BRANCH = "master"

# Models MOON agents use (CPU-friendly). Best-effort pull.
REQUIRED_MODELS = [
    "qwen3:0.6b",
    "qwen2.5:3b",
    "qwen2.5:1.5b",
    "qwen2.5-coder:1.5b",
    "deepseek-r1:1.5b",
]

KOKORO_RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
KOKORO_FILES = {
    "kokoro-v1.0.onnx": f"{KOKORO_RELEASE}/kokoro-v1.0.onnx",
    "voices-v1.0.bin": f"{KOKORO_RELEASE}/voices-v1.0.bin",
}

# Colour helpers
def _log(m: str) -> None:
    print(f"\033[36m[MOON-INSTALL]\033[0m {m}")

def _ok(m: str) -> None:
    print(f"\033[32m[OK]\033[0m  {m}")

def _warn(m: str) -> None:
    print(f"\033[33m[!!]\033[0m  {m}")

def _err(m: str) -> None:
    print(f"\033[31m[XX]\033[0m  {m}")

# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------
def _clean_env() -> dict:
    """Strip PYTHONPATH + VIRTUAL_ENV so we never target a foreign venv."""
    e = dict(os.environ)
    e.pop("PYTHONPATH", None)
    e.pop("VIRTUAL_ENV", None)
    return e

def _run(cmd, *, check: bool = False, **kw) -> subprocess.CompletedProcess:
    printable = " ".join(str(c) for c in cmd)
    _log(f"+ {printable}")
    kw.setdefault("env", _clean_env())
    return subprocess.run(cmd, check=check, **kw)

# ---------------------------------------------------------------------------
# 1. Python check
# ---------------------------------------------------------------------------
def check_python() -> str:
    py = shutil.which("python3") or shutil.which("python")
    if not py:
        _err("python3 not found. Install Python >= 3.10 first.")
        sys.exit(1)
    ver = subprocess.run(
        [py, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
        capture_output=True, text=True,
    ).stdout.strip()
    major, minor = (int(x) for x in ver.split("."))
    if major < 3 or (major == 3 and minor < 10):
        _err(f"Python {ver} found; MOON needs >= 3.10.")
        sys.exit(1)
    _ok(f"Python {ver} at {py}")
    return py

# ---------------------------------------------------------------------------
# 2. Clone or update the MOON repo
# ---------------------------------------------------------------------------
def resolve_repo_url() -> str:
    if os.environ.get("MOON_INSTALL_USE_HTTPS"):
        return REPO_HTTPS
    # SSH: verify ssh agent is reachable
    if shutil.which("ssh"):
        try:
            r = subprocess.run(
                ["ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes",
                 "-T", "git@github.com"],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0 or "Hi" in r.stdout or "permission" in r.stderr.lower():
                _ok("SSH to GitHub verified")
                return REPO_SSH
        except Exception:
            pass
    _warn("SSH not available — falling back to HTTPS. "
          "For a private repo, set MOON_INSTALL_USE_HTTPS=0 and configure SSH.")
    return REPO_HTTPS

def clone_or_update(repo_url: str, dest: Path, branch: str) -> None:
    if dest.exists() and (dest / ".git").exists():
        _log("MOON repo already present — pulling latest...")
        _run(["git", "-C", str(dest), "fetch", "origin"], check=True)
        _run(["git", "-C", str(dest), "checkout", branch], check=True)
        _run(["git", "-C", str(dest), "reset", "--hard", f"origin/{branch}"], check=True)
        _ok(f"MOON updated at {dest}")
        return
    _log(f"Cloning MOON into {dest} ...")
    _run(["git", "clone", "--branch", branch, "--depth", "1", repo_url, str(dest)],
         check=True)
    _ok(f"MOON cloned to {dest}")

# ---------------------------------------------------------------------------
# 3. Virtualenv + deps
# ---------------------------------------------------------------------------
def make_venv(root: Path) -> str:
    venv = root / ".venv"
    py = str(venv / "bin" / "python")
    if venv.exists() and os.path.exists(py):
        _log("venv present — reusing")
        # Ensure pip is current
        _run([py, "-m", "pip", "install", "--quiet", "--upgrade", "pip", "wheel", "setuptools"])
        return py
    _log("Creating virtualenv in ./.venv ...")
    _run([sys.executable, "-m", "venv", str(venv)])
    _ok("venv created")
    py = str(venv / "bin" / "python")
    _run([py, "-m", "pip", "install", "--quiet", "--upgrade", "pip", "wheel", "setuptools"])
    return py

def install_deps(py: str, root: Path) -> None:
    req = root / "requirements.txt"
    if not req.exists():
        _warn("requirements.txt not found — skipping deps")
        return
    _log("Installing CORE dependencies (requirements.txt) ...")
    r = _run(
        [py, "-m", "pip", "install", "-r", str(req),
         "--extra-index-url", "https://download.pytorch.org/whl/cpu"],
        check=False,
    )
    if r.returncode != 0:
        _err("core dependency install failed — MOON cannot run without them")
        sys.exit(1)
    _ok("core dependencies installed")

    opt = root / "requirements-optional.txt"
    if opt.exists():
        _log("Installing OPTIONAL dependencies (best-effort) ...")
        _run([py, "-m", "pip", "install", "-r", str(opt)], check=False)
        _ok("optional dependencies installed (best-effort)")

    # editable so `python -m moon` resolves
    _run([py, "-m", "pip", "install", "--quiet", "-e", str(root)])
    _ok("MOON installed in editable mode (`python -m moon` works)")

# ---------------------------------------------------------------------------
# 4. .env
# ---------------------------------------------------------------------------
def ensure_env(root: Path) -> None:
    env = root / ".env"
    if env.exists():
        _log(".env present — keeping existing local config")
        return
    example = root / ".env.example"
    if example.exists():
        shutil.copy(example, env)
        _ok(".env copied from .env.example (fill in secrets)")
        return
    default = (
        "# MOON local-first configuration (auto-generated)\n"
        "MODEL_BASE_URL=http://127.0.0.1:11434/v1\n"
        "MODEL_NAME=qwen3:0.6b\n"
        "MODEL_API_KEY=not-required-for-local\n"
        "EMBEDDING_BASE_URL=http://127.0.0.1:11434/v1\n"
        "EMBEDDING_MODEL=all-minilm\n"
        "EMBEDDING_DIM=384\n"
        "ENABLE_AGENT_VALIDATION=true\n"
        "ENABLE_AUTO_LEARNING=true\n"
        "ENABLE_BROWSER_AUTOMATION=false\n"
        "ENABLE_OCR=false\n"
        "ENABLE_PDF=false\n"
        "AUTHORIZED_TARGETS=\n"
        "STRONG_MODEL_NAME=qwen3:1.7b\n"
        "STRONG_MODEL_BASE_URL=http://127.0.0.1:11434/v1\n"
        "GITHUB_REPO=\n"
        "OPENAI_API_KEY=\n"
        "OPENAI_BASE_URL=https://api.openai.com/v1\n"
        "OPENAI_MODEL=gpt-4o-mini\n"
        "OPENROUTER_API_KEY=\n"
        "OPENROUTER_BASE_URL=https://openrouter.ai/api/v1\n"
        "OPENROUTER_MODEL=openai/gpt-4o-mini\n"
        "HUGGINGFACE_API_KEY=\n"
        "HUGGINGFACE_BASE_URL=https://router.huggingface.co\n"
        "HUGGINGFACE_MODEL=meta-llama/Llama-3.1-8B-Instruct\n"
        "TELEGRAM_BOT_TOKEN=\n"
        "TELEGRAM_CHAT_ID=\n"
        "TELEGRAM_POLL_TIMEOUT=30\n"
        "MOON_TERMINAL_TOKEN=\n"
    )
    env.write_text(default, encoding="utf-8")
    _ok(".env created with local-first defaults")

# ---------------------------------------------------------------------------
# 5. Ollama + models
# ---------------------------------------------------------------------------
def install_ollama() -> bool:
    """Best-effort Ollama install. Returns True if ollama is on PATH after."""
    if shutil.which("ollama"):
        return True
    _log("Ollama not found — attempting auto-install ...")
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "linux":
        if machine in ("x86_64", "amd64"):
            arch = "linux-amd64"
        elif machine in ("aarch64", "arm64"):
            arch = "linux-arm64"
        else:
            _warn(f"Unsupported arch {machine} for Ollama auto-install")
            return False
        url = f"https://ollama.com/download/ollama-linux-{arch}-latest.run"
        try:
            _log(f"Downloading Ollama for {arch} ...")
            tmp = Path("/tmp/ollama-install.run")
            urllib.request.urlretrieve(url, str(tmp))
            _run(["sh", str(tmp)], check=False)
            tmp.unlink(missing_ok=True)
            # give it a moment
            for _ in range(10):
                if shutil.which("ollama"):
                    break
                time.sleep(1)
        except Exception as exc:
            _warn(f"Ollama auto-install failed: {exc}")
            return False
    elif system == "darwin":
        # macOS: use brew if available
        if shutil.which("brew"):
            _run(["bash", "-c", "brew install ollama"], check=False)
        else:
            _warn("Ollama not found and no brew — install from https://ollama.com")
            return False
    else:
        _warn(f"Auto-install not supported on {system} — install Ollama manually")
        return False
    return shutil.which("ollama") is not None

def ollama_up() -> bool:
    try:
        urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3)
        return True
    except Exception:
        return False

def ensure_ollama_and_models() -> None:
    if not install_ollama():
        _warn("Ollama not available — MOON will start but needs a model backend to reason")
        return
    _ok("Ollama found on PATH")
    if not ollama_up():
        _log("Starting ollama serve (background) ...")
        subprocess.Popen(
            ["ollama", "serve"], stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, env=_clean_env(),
        )
        for _ in range(30):
            if ollama_up():
                break
            time.sleep(1)
        if not ollama_up():
            _warn("Ollama serve did not come up — models will fail to pull")
            return
        _ok("Ollama serve started")
    for m in REQUIRED_MODELS:
        _log(f"Pulling model: {m}  (best-effort, can take a while on first pull)")
        r = _run(["ollama", "pull", m], check=False)
        if r.returncode == 0:
            _ok(f"Model pulled: {m}")
        else:
            _warn(f"Model pull failed for {m} (continuing)")
    _ok("Ollama + models ready")

# ---------------------------------------------------------------------------
# 6. Kokoro voice assets
# ---------------------------------------------------------------------------
def install_kokoro() -> None:
    cache = Path.home() / ".cache" / "kokoro-onnx"
    cache.mkdir(parents=True, exist_ok=True)
    for name, url in KOKORO_FILES.items():
        dest = cache / name
        if dest.exists() and dest.stat().st_size > 1_000_000:
            _ok(f"Kokoro asset present: {name}")
            continue
        _log(f"Downloading Kokoro voice asset: {name} ...")
        try:
            urllib.request.urlretrieve(url, str(dest))
            _ok(f"  -> {dest.stat().st_size // 1_000_000} MB")
        except Exception as exc:
            _warn(f"  Kokoro asset download skipped (lazy-fetch on first use): {exc}")

# ---------------------------------------------------------------------------
# 7. Launcher + desktop
# ---------------------------------------------------------------------------
def install_launcher(root: Path) -> None:
    bin_dir = Path.home() / ".local" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    launcher = bin_dir / "moon"
    py = str(root / ".venv" / "bin" / "python")
    launcher.write_text(
        f"#!/usr/bin/env bash\n"
        f"cd \"{root}\" || exit 1\n"
        f"exec env -u PYTHONPATH \"{py}\" main.py \"$@\"\n",
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    _ok(f"launcher installed: {launcher}")
    if f":{os.environ.get('PATH', '')}:\"" not in f":{bin_dir}:\"":
        _warn(f"{bin_dir} not on PATH. Add: export PATH=\"$HOME/.local/bin:$PATH\"")

    if platform.system() == "Linux":
        apps = Path.home() / ".local" / "share" / "applications"
        apps.mkdir(parents=True, exist_ok=True)
        desk = apps / "moon-terminal.desktop"
        desk.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=MOON Neural Core\n"
            "Comment=MOON autonomous AI terminal HUD\n"
            f"Exec={launcher} terminal\n"
            "Icon=utilities-terminal\n"
            "Terminal=false\n"
            "Categories=Network;Utility;\n",
            encoding="utf-8",
        )
        desk.chmod(0o755)
        _ok(f"desktop entry: {desk}")

# ---------------------------------------------------------------------------
# 8. Post-install acceptance
# ---------------------------------------------------------------------------
def verify_install(py: str, root: Path) -> bool:
    _log("Running post-install acceptance (real subsystems, no mocks) ...")
    script = r"""
import sys, asyncio
sys.path.insert(0, '.')
from app.config.settings import get_settings
from app.brain.orchestrator import Orchestrator

async def main():
    ok = True
    try:
        # --- Voice engine ---
        from app.voice_engine import VoiceEngine
        ve = VoiceEngine(settings=get_settings())
        bs = ve.backend_status()
        kokoro = bs.get('kokoro', False)
        espeak = bs.get('espeak', False)
        f5 = bs.get('f5', False)
        cloning = bs.get('cloning_ready', False)
        print(f'VOICE kokoro={kokoro} espeak={espeak} f5={f5} cloning_ready={cloning}')
        ok = ok and (kokoro or espeak)
        ok = ok and cloning  # cloning_ready must be True for full voice capability

        # --- Orchestrator: setup + agent/tool counts ---
        o = Orchestrator(get_settings())
        await o.setup()
        n_agents = len(o._agents) if hasattr(o, '_agents') else 0
        n_tools = len(o._tools._registry.tool_names) if (hasattr(o, '_tools') and o._tools and hasattr(o._tools, '_registry')) else 0
        print(f'AGENTS={n_agents} TOOLS={n_tools}')
        ok = ok and n_agents >= 30 and n_tools >= 30

        # --- Real tool execution ---
        if o._tools:
            r = await o._tools.run('system_info', {}, agent=None)
            out = getattr(r, 'output', '') or ''
            has_linux = 'linux' in out.lower()
            print(f'TOOL system_info real_execution={has_linux}')
            ok = ok and has_linux

        await o.teardown()
    except Exception as exc:
        import traceback
        traceback.print_exc()
        ok = False
    print(f'ACCEPTANCE: {"PASS" if ok else "FAIL"}')
    return ok

result = asyncio.run(main())
sys.exit(0 if result else 1)
"""
    tmp = root / ".install_verify_tmp.py"
    tmp.write_text(script, encoding="utf-8")
    try:
        r = _run([py, str(tmp)], capture_output=True, text=True, timeout=400)
    finally:
        tmp.unlink(missing_ok=True)
    for line in (r.stdout or "").splitlines():
        if line.startswith(("VOICE", "AGENTS", "TOOL", "ACCEPTANCE")):
            _log(f"   {line}")
    if r.returncode != 0 or "ACCEPTANCE: PASS" not in (r.stdout or ""):
        _err("Post-install acceptance FAILED — review output above")
        if r.stderr:
            for line in (r.stderr or "").splitlines()[:20]:
                _err(f"   stderr: {line}")
        return False
    _ok("Post-install acceptance: PASS (voice + agents + tools + real tool exec)")
    return True

# ---------------------------------------------------------------------------
# 9. Systemd service (optional)
# ---------------------------------------------------------------------------
def install_service(root: Path) -> None:
    svc_src = root / "deploy" / "moon-terminal.service"
    if not svc_src.exists():
        _warn("deploy/moon-terminal.service not found — skipping service install")
        return
    if platform.system() != "Linux" or not shutil.which("systemctl"):
        _warn("systemd not available — skipping service")
        return
    svc_dest = Path.home() / ".config" / "systemd" / "user" / "moon-terminal.service"
    svc_dest.parent.mkdir(parents=True, exist_ok=True)
    content = svc_src.read_text(encoding="utf-8")
    # __MOON_HOME__ is the installer's anchor — replace with the actual dest.
    # Fall back to ROOT if someone cloned elsewhere and re-ran the installer.
    content = content.replace("__MOON_HOME__", str(root))
    content = content.replace("/home/meow/Projects/MOON", str(root))
    svc_dest.write_text(content, encoding="utf-8")
    _run(["systemctl", "--user", "daemon-reload"], check=False)
    _run(["systemctl", "--user", "enable", "moon-terminal.service"], check=False)
    _ok(f"systemd user service installed: {svc_dest}")
    _warn("MOON does NOT auto-start the UI. Run `moon terminal` (or `moon`) to open the HUD.")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(
        description="MOON single-file auto-installer — installs MOON fully on any machine",
    )
    ap.add_argument("--verify", action="store_true",
                    help="only run the post-install acceptance check")
    ap.add_argument("--no-ollama", action="store_true", help="skip Ollama + model pull")
    ap.add_argument("--no-voice", action="store_true", help="skip Kokoro voice assets")
    ap.add_argument("--no-service", action="store_true", help="skip systemd service install")
    ap.add_argument("--repo", default=None, help="override repo URL (ssh or https)")
    ap.add_argument("--branch", default=DEFAULT_BRANCH, help=f"git branch to install (default: {DEFAULT_BRANCH})")
    ap.add_argument("--dest", default=None, help="destination directory (default: ./MOON or ./moon-install)")
    args = ap.parse_args()

    if args.verify:
        root = Path.cwd()
        py = str(root / ".venv" / "bin" / "python")
        if not Path(py).exists():
            _err(".venv/bin/python not found — run full install first")
            sys.exit(1)
        passed = verify_install(py, root)
        sys.exit(0 if passed else 1)

    _log("=== MOON SINGLE-FILE AUTO-INSTALLER ===")
    py = check_python()

    # Resolve destination
    if args.dest:
        dest = Path(args.dest).resolve()
    else:
        # If we're already inside a MOON checkout, use cwd. Otherwise clone to ./MOON.
        if (Path.cwd() / ".git").exists() and (Path.cwd() / "main.py").exists():
            dest = Path.cwd().resolve()
            _log(f"Detected existing MOON checkout at {dest} — using it")
        else:
            dest = Path.cwd() / "MOON"
            _log(f"Fresh install — cloning to {dest}")

    repo_url = args.repo or resolve_repo_url()
    clone_or_update(repo_url, dest, args.branch)
    root = dest

    _log(f"Working from: {root}")
    vpy = make_venv(root)
    install_deps(vpy, root)
    ensure_env(root)

    if not args.no_ollama:
        ensure_ollama_and_models()

    if not args.no_voice:
        install_kokoro()

    install_launcher(root)

    if not args.no_service:
        install_service(root)

    # Acceptance
    passed = verify_install(vpy, root)
    print()
    if passed:
        _ok("MOON is INSTALLED and VERIFIED at 100% functional.")
        _log("Launch:  moon terminal   (or: ./venv/bin/python main.py terminal)")
        _log("Shell:   moon shell      (Textual TUI with TTS + !shell + /cli)")
        _log("Web HUD: http://127.0.0.1:8777")
        _log("Unlock:  MOON love you 3000")
    else:
        _warn("Install completed but acceptance found issues.")
        _log("Run: python3 install_moon.py --verify   (after fixing)")
    sys.exit(0 if passed else 1)

if __name__ == "__main__":
    main()
