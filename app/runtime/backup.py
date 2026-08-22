"""Cross-platform backup & restore (spec 25).

Pure-Python, ``pathlib``-based implementation that replaces the bash
``scripts/backup.sh`` wrapper with the same behaviour portable to Linux,
macOS and Windows. It snapshots MOON's runtime data (agents, knowledge,
memory, skills, evaluations, logs, the agent_factory sqlite DB and the
optional ``moon_settings.json``) into a timestamped archive directory.

Design rules (non-destructive):
- Never deletes project source files.
- Never overwrites real secrets (``.env`` is explicitly excluded from backups;
  operators back up ``.env`` themselves -- see README).
- Safe to run repeatedly; each run gets a fresh timestamped directory.
- Restore copies a snapshot back over the live ``data/`` tree.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Directories/files under the project root that constitute runtime DATA.
# Source code, agents' *definitions* and config templates are version-controlled
# separately; this module only handles generated/runtime state.
DATA_DIRS = ["data", "capabilities", "connections", "voices"]
DATA_FILES = ["data/agents/agent_factory.db", "data/executions.db", "moon_settings.json"]


def _project_root() -> Path:
    # This module lives in app/runtime; the project root is two levels up.
    return Path(__file__).resolve().parent.parent.parent


def _snapshot_name() -> str:
    return "moon_" + datetime.now().strftime("%Y%m%d_%H%M%S")


def backup(dest_root: Optional[Path] = None) -> Path:
    """Create a timestamped backup of MOON runtime data. Returns the backup dir."""
    root = _project_root()
    dest_root = dest_root or (root / "backups")
    dest = dest_root / _snapshot_name()
    dest.mkdir(parents=True, exist_ok=True)

    # Back up whole runtime data directories that exist.
    for d in DATA_DIRS:
        src = root / d
        if src.is_dir():
            shutil.copytree(src, dest / d, dirs_exist_ok=True)

    # Back up individual runtime files that exist.
    for f in DATA_FILES:
        src = root / f
        if src.is_file():
            (dest / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest / f)

    # Persist a manifest of what was captured.
    manifest = dest / "BACKUP_MANIFEST.txt"
    captured = sorted(str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file())
    manifest.write_text(
        "MOON runtime backup\n"
        f"created: {datetime.now().isoformat()}\n"
        f"source_root: {root}\n"
        f"items: {len(captured)}\n"
        + "\n".join(captured),
        encoding="utf-8",
    )
    return dest


def restore(snapshot: Path, root: Optional[Path] = None) -> list[str]:
    """Restore a backup snapshot over the live runtime data. Returns restored paths."""
    root = root or _project_root()
    snapshot = Path(snapshot)
    if not snapshot.is_dir():
        raise FileNotFoundError(f"backup snapshot not found: {snapshot}")
    restored: list[str] = []
    for d in DATA_DIRS:
        src = snapshot / d
        if src.is_dir():
            shutil.copytree(src, root / d, dirs_exist_ok=True)
            restored.append(d)
    for f in DATA_FILES:
        src = snapshot / f
        if src.is_file():
            (root / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, root / f)
            restored.append(f)
    return restored


def _cli() -> int:
    ap = argparse.ArgumentParser(description="MOON runtime backup/restore (Python, cross-platform)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("backup", help="Snapshot runtime data into backups/")
    rp = sub.add_parser("restore", help="Restore a snapshot over live data")
    rp.add_argument("snapshot", help="Path to a backups/moon_<timestamp> directory")
    args = ap.parse_args()
    if args.cmd == "backup":
        d = backup()
        print(f"BACKUP COMPLETE -> {d}")
        return 0
    if args.cmd == "restore":
        restored = restore(Path(args.snapshot))
        print(f"RESTORE COMPLETE -> restored: {', '.join(restored) or 'nothing'}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(_cli())
