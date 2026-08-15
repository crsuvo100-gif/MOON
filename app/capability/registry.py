"""CapabilityRegistry -- persistent, session-surviving capability store.

Layout (under <repo>/capabilities/):
  capabilities/
    registry.json     -- machine-readable capability index
    manifests/        -- one JSON manifest per capability
    installed/        -- local shims / generated plugins for acquired tools
    cache/            -- memoized GitHub search / inspection results

The registry is the single source of truth for "what does MOON already have"
so MOON never re-downloads or re-installs a verified capability.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CAP_ROOT = Path(__file__).resolve().parent.parent.parent / "capabilities"


@dataclass
class CapabilityRecord:
    name: str
    version: str = "unknown"
    status: str = "unknown"          # unknown | installed | verified | failed
    source: str = "unknown"          # system-package | pip | npm | github | ...
    runtime: str = "native"          # native | python | node | go | ...
    source_url: str = ""
    repository: str = ""             # owner/repo for github sources
    install_method: str = ""
    permissions: tuple[str, ...] = field(default_factory=tuple)
    network_required: bool = False
    sandbox_required: bool = True
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    verified_at: str = ""
    health: str = "unknown"          # healthy | degraded | unhealthy
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CapabilityRecord":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


class CapabilityRegistry:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else _CAP_ROOT
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "manifests").mkdir(exist_ok=True)
        (self.root / "installed").mkdir(exist_ok=True)
        (self.root / "cache").mkdir(exist_ok=True)
        self._index = self.root / "registry.json"
        self._records: dict[str, CapabilityRecord] = {}
        self._load()

    # ------------------------------------------------------------------
    def _load(self) -> None:
        if self._index.exists():
            try:
                data = json.loads(self._index.read_text(encoding="utf-8"))
                for name, rec in (data.get("capabilities") or {}).items():
                    self._records[name] = CapabilityRecord.from_dict(rec)
            except Exception as exc:  # noqa: BLE001
                logger.warning("capability registry load failed: %s", exc)

    def _save(self) -> None:
        data = {
            "version": 1,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "capabilities": {n: r.to_dict() for n, r in self._records.items()},
        }
        self._index.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    def get(self, name: str) -> CapabilityRecord | None:
        return self._records.get(name)

    def all(self) -> list[CapabilityRecord]:
        return list(self._records.values())

    def has(self, name: str) -> bool:
        return name in self._records

    def is_verified(self, name: str) -> bool:
        rec = self._records.get(name)
        return bool(rec and rec.status == "verified" and rec.health == "healthy")

    def upsert(self, rec: CapabilityRecord) -> None:
        self._records[rec.name] = rec
        self._save()
        # also persist the manifest
        try:
            (self.root / "manifests" / f"{rec.name}.json").write_text(
                json.dumps(rec.to_dict(), indent=2), encoding="utf-8"
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("manifest write skipped: %s", exc)

    def health(self, name: str) -> str:
        rec = self._records.get(name)
        return rec.health if rec else "unknown"

    def remove(self, name: str) -> bool:
        if name in self._records:
            del self._records[name]
            self._save()
            m = self.root / "manifests" / f"{name}.json"
            if m.exists():
                m.unlink()
            return True
        return False

    def cache_put(self, key: str, value: Any) -> None:
        try:
            (self.root / "cache" / f"{key}.json").write_text(
                json.dumps(value, default=str), encoding="utf-8"
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("cache put skipped: %s", exc)

    def cache_get(self, key: str) -> Any | None:
        p = self.root / "cache" / f"{key}.json"
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                return None
        return None
