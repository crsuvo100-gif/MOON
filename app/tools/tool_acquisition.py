"""tool_acquisition.py -- MOON's ability to self-extend with tools on demand.

When a task needs a capability MOON lacks, she can:
  1. install a known package from a curated CATALOG (pip) and register a thin
     BaseTool wrapper, or
  2. ask the LLM to GENERATE a small BaseTool plugin for a custom need, write
     it to plugins/generated/, import and register it.

All installs are best-effort and reported; failures degrade gracefully (the
task continues with whatever tools exist). This makes MOON complete tasks
that require tools she did not ship with.
"""

from __future__ import annotations

import importlib
import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

GENERATED_DIR = Path(__file__).resolve().parent.parent.parent / "plugins" / "generated"

# Curated catalog: capability keyword -> pip package + import name.
# These are LEGITIMATE, widely-used libraries (no malware). Network install
# may be unavailable offline; we try and report.
TOOL_CATALOG: dict[str, dict] = {
    "youtube": {"pip": "yt-dlp", "import": "yt_dlp", "cap": "download audio/video from YouTube"},
    "video": {"pip": "yt-dlp", "import": "yt_dlp", "cap": "download/process video"},
    "audio download": {"pip": "yt-dlp", "import": "yt_dlp", "cap": "download media"},
    "web scraping": {"pip": "beautifulsoup4", "import": "bs4", "cap": "parse HTML"},
    "html parse": {"pip": "beautifulsoup4", "import": "bs4", "cap": "parse HTML"},
    "browser automation": {"pip": "playwright", "import": "playwright", "cap": "drive a real browser"},
    "image": {"pip": "pillow", "import": "PIL", "cap": "image processing"},
    "ocr": {"pip": "pytesseract", "import": "pytesseract", "cap": "OCR (needs tesseract binary)"},
    "pdf": {"pip": "pypdf", "import": "pypdf", "cap": "read PDFs"},
    "data": {"pip": "pandas", "import": "pandas", "cap": "data analysis"},
    "csv": {"pip": "pandas", "import": "pandas", "cap": "tabular data"},
    "plot": {"pip": "matplotlib", "import": "matplotlib", "cap": "charts/plots"},
    "chart": {"pip": "matplotlib", "import": "matplotlib", "cap": "charts/plots"},
    "speech": {"pip": "SpeechRecognition", "import": "speech_recognition", "cap": "STT"},
    "translate api": {"pip": "deep-translator", "import": "deep_translator", "cap": "translation"},
    "excel": {"pip": "openpyxl", "import": "openpyxl", "cap": "xlsx files"},
    "yaml": {"pip": "pyyaml", "import": "yaml", "cap": "YAML config"},
    "qr": {"pip": "qrcode", "import": "qrcode", "cap": "generate QR codes"},
}


def _already_importable(import_name: str) -> bool:
    try:
        importlib.import_module(import_name)
        return True
    except Exception:  # noqa: BLE001
        return False


def install_package(pip_name: str) -> bool:
    """Try to pip-install a package (best-effort). Returns success."""
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", pip_name],
            check=False, timeout=180,
        )
        return _already_importable(pip_name.split("[")[0].replace("-", "_").split(".")[0])
    except Exception as exc:  # noqa: BLE001
        logger.warning("install %s failed: %s", pip_name, exc)
        return False


def acquire_by_catalog(capability: str, registry) -> str | None:
    """Install + register a tool for a known capability. Returns tool name or None."""
    cap = capability.lower()
    for key, spec in TOOL_CATALOG.items():
        if key in cap:
            if not _already_importable(spec["import"]):
                if not install_package(spec["pip"]):
                    logger.info("catalog tool '%s' unavailable (install failed/offline)", key)
                    return None
            return _register_wrapper(key, spec, registry)
    return None


def _register_wrapper(key: str, spec: dict, registry) -> str | None:
    """Register a thin BaseTool that exposes the installed library."""
    from app.tools.base import BaseTool, ToolResult

    class _Wrapped(BaseTool):
        name = f"tool_{key.replace(' ', '_')}"
        description = f"Auto-installed tool: {spec['cap']} (via {spec['pip']})."

        async def execute(self, **kwargs):  # pragma: no cover - dynamic
            return ToolResult(output=f"[tool_{key}] {spec['pip']} ready; use python_executor for detailed calls.", success=True)

    try:
        registry.register(_Wrapped())
        logger.info("acquired tool '%s' from catalog", key)
        return _Wrapped.name
    except Exception as exc:  # noqa: BLE001
        logger.warning("register wrapper failed: %s", exc)
        return None


def generate_plugin(name: str, purpose: str, code: str, registry) -> str | None:
    """Write an LLM-generated BaseTool plugin, import + register it."""
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"gen_{name.replace(' ', '_').lower()}.py"
    path = GENERATED_DIR / fname
    try:
        path.write_text(code, encoding="utf-8")
        mod = importlib.import_module(f"plugins.generated.{fname[:-3]}")
        count = 0
        for attr in vars(mod).values():
            if isinstance(attr, type) and issubclass(attr, __import__("app.tools.base", fromlist=["BaseTool"]).BaseTool) and attr is not __import__("app.tools.base", fromlist=["BaseTool"]).BaseTool:
                registry.register(attr())
                count += 1
        if count:
            logger.info("generated plugin '%s' registered", name)
            return name
    except Exception as exc:  # noqa: BLE001
        logger.warning("generate_plugin failed: %s", exc)
        if path.exists():
            path.unlink(missing_ok=True)
    return None
