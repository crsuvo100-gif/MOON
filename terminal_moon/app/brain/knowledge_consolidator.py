"""
Stub: knowledge consolidator (seeds KB from LTM when enabled).
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("moontm.consolidator")


class KnowledgeConsolidator:
    """Best-effort consolidation of recent interactions into the KB."""

    def __init__(self, memory: Optional[Any] = None, ltm_path: Optional[str] = None) -> None:
        self._memory = memory

    async def consolidate(self) -> None:
        if not self._memory:
            return
        logger.info("KnowledgeConsolidator: consolidation tick (best-effort)")
        # In a full implementation: read recent LTM entries, re-index into KB
