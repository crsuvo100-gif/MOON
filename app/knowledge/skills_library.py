"""skills_library.py -- index the bundled Hermes skill corpus into MOON's KB.

The corpus under skills/ (copied from the environment backup) contains 100+
Hermes SKILL.md instruction sets. Indexing them makes that know-how
retrievable via MOON's semantic recall, so the skills are functionally
available to her (not just dead files on disk).
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"


async def index_skills(knowledge_base) -> int:
    """Index every SKILL.md in the corpus. Returns number indexed."""
    if not SKILLS_DIR.exists():
        logger.info("skills/ dir absent; skipping skills index")
        return 0
    count = 0
    for skill_md in sorted(SKILLS_DIR.glob("*/SKILL.md")) + sorted(SKILLS_DIR.glob("*/*/SKILL.md")):
        try:
            text = skill_md.read_text(errors="replace")
            rel = skill_md.relative_to(SKILLS_DIR)
            doc_id = f"skill_{rel}".replace("/", "_").replace(".md", "")
            await knowledge_base.index_document(doc_id, text)
            count += 1
        except Exception as exc:  # noqa: BLE001
            logger.debug("skill index skip %s: %s", skill_md, exc)
    logger.info("Indexed %d skills into knowledge base", count)
    return count
