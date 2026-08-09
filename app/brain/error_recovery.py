"""ErrorRecovery -- bounded retry policy for failures."""

from __future__ import annotations


class ErrorRecovery:
    def __init__(self, max_retries: int = 3) -> None:
        self.max_retries = max_retries

    def should_retry(self, attempt: int) -> bool:
        return attempt < self.max_retries
