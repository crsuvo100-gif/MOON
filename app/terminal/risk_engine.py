"""Risk engine – determines a risk level for an ExecutionRequest.

It loads ``risk_policy.yaml`` (placed in ``app/terminal``) and evaluates the
sanitized command using token‑aware matching to avoid false positives.
"""

import yaml
import re
import shlex
from pathlib import Path

from .security import sanitize_command
from .models import ExecutionRequest

class RiskEngine:
    def __init__(self, policy_path: Path = Path(__file__).with_name("risk_policy.yaml")):
        # Load risk policy
        self.policy = yaml.safe_load(policy_path.read_text())
        # Store raw pattern strings for token‑aware matching
        self.patterns = {level: pats for level, pats in self.policy.items() if level != "auto_allow"}
        # Pre‑compile regexes for efficiency
        self.compiled = {level: [re.compile(p) for p in pats] for level, pats in self.patterns.items()}
        self.auto_allow = set(self.policy.get("auto_allow", []))

    def _matches_pattern(self, tokens: list[str], pattern_str: str, regex: re.Pattern) -> bool:
        """Return True if *pattern_str* matches the token list.

        - If the pattern contains whitespace, join tokens with spaces and apply the
          regex (covers multi‑token patterns like ``"rm -rf"``).
        - For single‑token patterns we require a full‑match against any individual token
          to avoid false positives such as ``"skill"`` matching ``"kill"``.
        """
        if re.search(r"\s", pattern_str):
            joined = " ".join(tokens)
            return bool(regex.search(joined))
        else:
            return any(regex.fullmatch(tok) for tok in tokens)

    def evaluate(self, req: ExecutionRequest) -> str:
        """Return risk level ("low", "medium", "high") for a request.

        The command is first sanitized to redact secrets, then tokenised with
        ``shlex`` to respect quoting/escaping. Auto‑allowed commands are forced to
        low risk.
        """
        # Sanitize command to redact secrets before risk evaluation
        sanitized = sanitize_command(req.command).strip()
        # Tokenise respecting quoting/escaping; fallback to full string on error
        try:
            tokens = shlex.split(sanitized)
        except ValueError:
            tokens = [sanitized]

        # Auto‑allow exact command strings
        if sanitized in self.auto_allow:
            return "low"

        for level in ("high_risk", "medium_risk", "low_risk"):
            for pattern_str, regex in zip(self.patterns.get(level, []), self.compiled.get(level, [])):
                if self._matches_pattern(tokens, pattern_str, regex):
                    return level.split("_")[0]  # "high", "medium", "low"
        return "low"  # default fallback