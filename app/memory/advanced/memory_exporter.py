"""Memory exporter -- export memories to various formats.

Professional AI assistants need to export their memories for backup,
sharing, migration, or analysis. This module exports memories to:

1. JSON: Full fidelity, machine-readable, includes all metadata.
2. Markdown: Human-readable, organized by topic/tags.
3. CSV: Spreadsheet-friendly, one row per memory.
4. Text: Plain text, simple format for LLM consumption.

Usage:
    exporter = MemoryExporter(memory_manager)
    json_output = exporter.to_json()
    md_output = exporter.to_markdown()
    csv_output = exporter.to_csv()
    text_output = exporter.to_text()

    # Export to file
    exporter.export_to_file("backup.json", format="json")
"""

from __future__ import annotations

import csv
import io
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ExportResult:
    """Result of an export operation."""
    format: str
    content: str
    memory_count: int
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "memory_count": self.memory_count,
            "content_length": len(self.content),
            "timestamp": self.timestamp,
        }


class MemoryExporter:
    """Exports memories to various formats.

    Supports JSON, Markdown, CSV, and plain text output.
    """

    def __init__(self, memory_manager=None) -> None:
        self._mm = memory_manager

    async def to_json(self, include_metadata: bool = True) -> ExportResult:
        """Export all memories to JSON format.

        Args:
            include_metadata: Include full metadata (tags, timestamps, etc.)

        Returns:
            ExportResult with JSON content.
        """
        data = await self._gather_all_memories()
        export_data: dict[str, Any] = {
            "exported_at": time.time(),
            "memory_count": len(data),
            "memories": data,
        }

        if not include_metadata:
            # Strip metadata, keep only content
            for mem in export_data["memories"]:
                mem.pop("metadata", None)
                mem.pop("tags", None)

        content = json.dumps(export_data, indent=2, ensure_ascii=False, default=str)
        return ExportResult(
            format="json",
            content=content,
            memory_count=len(data),
        )

    async def to_markdown(self) -> ExportResult:
        """Export memories to Markdown, organized by tags.

        Returns:
            ExportResult with Markdown content.
        """
        memories = await self._gather_all_memories()

        # Group by primary tag
        by_tag: dict[str, list[dict[str, Any]]] = {}
        for mem in memories:
            tags = mem.get("tags", [])
            primary_tag = tags[0] if tags else "untagged"
            by_tag.setdefault(primary_tag, []).append(mem)

        lines: list[str] = [
            "# MOON Memory Export",
            "",
            f"Exported: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())}",
            f"Total memories: {len(memories)}",
            "",
            "---",
            "",
        ]

        for tag in sorted(by_tag.keys()):
            lines.append(f"## {tag}")
            lines.append("")
            for mem in by_tag[tag]:
                content = mem.get("content", "")
                lines.append(f"### {content[:80]}")
                lines.append("")
                lines.append(content)
                lines.append("")
                if mem.get("metadata"):
                    lines.append(f"**Metadata:** `{json.dumps(mem['metadata'], default=str)}`")
                    lines.append("")
                lines.append("---")
                lines.append("")

        content = "\n".join(lines)
        return ExportResult(
            format="markdown",
            content=content,
            memory_count=len(memories),
        )

    async def to_csv(self) -> ExportResult:
        """Export memories to CSV format.

        Columns: id, content, tags, source, importance, created_at

        Returns:
            ExportResult with CSV content.
        """
        memories = await self._gather_all_memories()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "content", "tags", "source", "importance", "created_at"])

        for mem in memories:
            writer.writerow([
                mem.get("id", ""),
                mem.get("content", ""),
                "|".join(mem.get("tags", [])),
                mem.get("source", ""),
                mem.get("importance", 0.5),
                mem.get("created_at", ""),
            ])

        content = output.getvalue()
        return ExportResult(
            format="csv",
            content=content,
            memory_count=len(memories),
        )

    async def to_text(self, max_length: int = 5000) -> ExportResult:
        """Export memories to plain text, optimized for LLM consumption.

        Args:
            max_length: Maximum characters to include.

        Returns:
            ExportResult with plain text content.
        """
        memories = await self._gather_all_memories()

        lines: list[str] = [
            "MOON MEMORY EXPORT",
            f"Total: {len(memories)} memories",
            "=" * 60,
            "",
        ]

        current_length = 0
        included = 0
        for mem in memories:
            content = mem.get("content", "")
            tags = ", ".join(mem.get("tags", []))
            entry = f"[{tags}] {content}\n\n"
            if current_length + len(entry) > max_length:
                lines.append(f"\n... ({len(memories) - included} more memories truncated)")
                break
            lines.append(entry)
            current_length += len(entry)
            included += 1

        content = "\n".join(lines)
        return ExportResult(
            format="text",
            content=content,
            memory_count=included,
        )

    async def _gather_all_memories(self) -> list[dict[str, Any]]:
        """Gather all memories from all subsystems into a unified list."""
        memories: list[dict[str, Any]] = []
        if self._mm is None:
            return memories

        try:
            # LTM entries
            if hasattr(self._mm, '_ltm'):
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    entries = loop.run_until_complete(self._mm._ltm.all())
                except RuntimeError:
                    entries = []
                for entry in entries:
                    inner = getattr(entry, 'entry', entry)
                    memories.append({
                        "id": entry.id,
                        "content": entry.content,
                        "tags": getattr(inner, 'tags', []),
                        "source": "ltm",
                        "importance": getattr(entry, 'importance', 0.5),
                        "created_at": getattr(inner, 'created_at', 0),
                        "metadata": getattr(inner, 'metadata', {}),
                    })
        except Exception as exc:
            logger.debug("Gather LTM failed: %s", exc)

        try:
            # Episodic memories
            if hasattr(self._mm, 'episodic'):
                for ep in self._mm.episodic._eps:
                    memories.append({
                        "id": f"ep_{id(ep)}",
                        "content": f"Goal: {ep.goal} | Outcome: {ep.outcome} | Lesson: {ep.lesson}",
                        "tags": ["episodic"],
                        "source": "episodic",
                        "importance": 1.0 if ep.success else 0.5,
                        "created_at": ep.ts,
                        "metadata": {"success": ep.success},
                    })
        except Exception as exc:
            logger.debug("Gather episodic failed: %s", exc)

        try:
            # STM items
            if hasattr(self._mm, '_stm'):
                stm = self._mm._stm
                if hasattr(stm, '_items'):
                    for item in stm._items:
                        content = item.content if hasattr(item, 'content') else str(item)
                        relevance = getattr(item, 'relevance', 0.5)
                        memories.append({
                            "id": f"stm_{id(item)}",
                            "content": content,
                            "tags": ["short_term"],
                            "source": "stm",
                            "importance": relevance,
                            "created_at": time.time(),
                            "metadata": {},
                        })
        except Exception as exc:
            logger.debug("Gather STM failed: %s", exc)

        return memories

    async def export_to_file(self, filepath: str, format: str = "json") -> ExportResult:
        """Export memories to a file.

        Args:
            filepath: Path to the output file.
            format: Export format ("json", "markdown", "csv", "text").

        Returns:
            ExportResult.
        """
        exporters = {
            "json": self.to_json,
            "markdown": self.to_markdown,
            "csv": self.to_csv,
            "text": self.to_text,
        }

        exporter = exporters.get(format)
        if exporter is None:
            raise ValueError(f"Unsupported format: {format}. Use: {list(exporters.keys())}")

        result = exporter()
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(result.content, encoding="utf-8")
        logger.info("Exported %d memories to %s (%s)", result.memory_count, filepath, format)
        return result

    def stats(self) -> dict[str, Any]:
        """Return exporter statistics."""
        return {
            "supported_formats": ["json", "markdown", "csv", "text"],
        }
