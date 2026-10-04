"""Memory backup / export / import (spec 46, 47, 48, 49).

Rules enforced here:
  * spec 48: secrets are NEVER exported, whatever the scope.
  * spec 47: rotation -- keep N, do not let backups grow without bound.
  * spec 49: import is validated (schema -> dedup -> security -> conflict) BEFORE
    anything is inserted.
  * spec 46: a backup preserves memory, metadata, versions and sync state.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.memory.record import MemoryRecord
from app.memory.security import detect_secret, sanitize
from app.memory.store import MemoryStore, default_db_path

logger = logging.getLogger(__name__)


def backup_dir() -> Path:
    d = Path(os.environ.get("MOON_BACKUP_PATH", "")
             or (default_db_path().parent / "backups"))
    return d


@dataclass
class ImportReport:
    received: int = 0
    inserted: int = 0
    duplicates: int = 0
    rejected_schema: int = 0
    rejected_secret: int = 0
    errors: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []

    def to_dict(self) -> dict[str, Any]:
        return {"received": self.received, "inserted": self.inserted,
                "duplicates": self.duplicates,
                "rejected_schema": self.rejected_schema,
                "rejected_secret": self.rejected_secret,
                "errors": self.errors[:10]}


# ---------------------------------------------------------------- spec 48
def export_records(store: MemoryStore, *, limit: int = 0,
                   include_archived: bool = True) -> list[dict[str, Any]]:
    """Export records as JSON-safe dicts with secrets masked (spec 48)."""
    rows = store.query(include_archived=include_archived, limit=limit or 100000)
    out: list[dict[str, Any]] = []
    for r in rows:
        d = r.to_dict()
        # spec 48: never export a secret, and mask anything that looks like one.
        if detect_secret(r.content).is_secret:
            logger.info("export: skipping secret-like record %s", r.memory_id)
            continue
        d["content"], _ = sanitize(r.content)
        d["summary"], _ = sanitize(r.summary or "")
        out.append(d)
    return out


def export_json(store: MemoryStore, path: str | Path, **kw: Any) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(export_records(store, **kw), indent=2, default=str),
                 encoding="utf-8")
    return p


def export_jsonl(store: MemoryStore, path: str | Path, **kw: Any) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for rec in export_records(store, **kw):
            fh.write(json.dumps(rec, default=str) + "\n")
    return p


# ---------------------------------------------------------------- spec 46/47
def create_backup(store: MemoryStore, *, name: str | None = None,
                  keep: int = 7) -> Path:
    """Full JSON snapshot + rotation (spec 46/47)."""
    d = backup_dir()
    d.mkdir(parents=True, exist_ok=True)
    stamp = name or time.strftime("moon_memory_%Y%m%d_%H%M%S")
    path = d / f"{stamp}.json"
    export_json(store, path)
    _rotate(d, keep=keep)
    return path


def _rotate(d: Path, *, keep: int) -> None:
    """spec 47: keep the newest N backups, drop the rest."""
    if keep <= 0:
        return
    snaps = sorted(d.glob("moon_memory_*.json"), key=lambda p: p.stat().st_mtime,
                   reverse=True)
    for old in snaps[keep:]:
        try:
            old.unlink()
            logger.info("backup rotation: removed %s", old.name)
        except OSError:
            pass


def list_backups() -> list[dict[str, Any]]:
    d = backup_dir()
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob("moon_memory_*.json"),
                    key=lambda x: x.stat().st_mtime, reverse=True):
        st = p.stat()
        out.append({"path": str(p), "name": p.name,
                    "size_bytes": st.st_size, "created_at": st.st_mtime})
    return out


def restore_backup(store: MemoryStore, path: str | Path) -> ImportReport:
    """spec 46: restore a snapshot through the validated import path."""
    return import_records(store, json.loads(Path(path).read_text(encoding="utf-8")))


# ---------------------------------------------------------------- spec 49
def import_records(store: MemoryStore, data: Any) -> ImportReport:
    """IMPORT -> SCHEMA VALIDATION -> DEDUP -> SECURITY -> CONFLICT -> INSERT."""
    rep = ImportReport()
    if isinstance(data, dict):
        data = data.get("records") or data.get("memories") or [data]
    if not isinstance(data, list):
        rep.errors.append("payload is not a list of records")
        return rep
    rep.received = len(data)

    existing = {r.memory_id: r for r in store.query(limit=100000,
                                                    include_archived=True)}
    for item in data:
        if not isinstance(item, dict) or "content" not in item:
            rep.rejected_schema += 1
            continue
        # SECURITY before anything else (spec 43/49)
        if detect_secret(str(item.get("content", ""))).is_secret:
            rep.rejected_secret += 1
            continue
        try:
            rec = MemoryRecord.from_dict(item)
        except Exception as exc:  # noqa: BLE001
            rep.rejected_schema += 1
            rep.errors.append(f"schema: {exc}")
            continue
        # DEDUP/CONFLICT: an existing id with different content is a conflict --
        # keep the newer version rather than silently overwriting (spec 36/38).
        prev = existing.get(rec.memory_id)
        if prev is not None:
            if prev.content == rec.content:
                rep.duplicates += 1
                continue
            if rec.updated_at <= prev.updated_at:
                rep.duplicates += 1
                continue
        try:
            store.upsert(rec)
            rep.inserted += 1
        except Exception as exc:  # noqa: BLE001
            rep.errors.append(f"insert: {exc}")
    return rep


__all__ = [
    "export_records", "export_json", "export_jsonl", "create_backup",
    "restore_backup", "import_records", "list_backups", "backup_dir",
    "ImportReport",
]
