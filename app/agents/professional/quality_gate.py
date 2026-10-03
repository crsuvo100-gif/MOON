"""Output Quality Gate — multi-stage output validation.

Validates agent output through multiple quality stages before delivery.
Each stage checks a different aspect: correctness, completeness, safety,
and presentation. Failed outputs are routed for correction.
"""

from __future__ import annotations

import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


class QualityLevel(Enum):
    """Quality assessment levels."""
    EXCELLENT = "excellent"
    GOOD = "good"
    ACCEPTABLE = "acceptable"
    POOR = "poor"
    REJECTED = "rejected"


class QualityStage(Enum):
    """Quality check stages."""
    CORRECTNESS = "correctness"
    COMPLETENESS = "completeness"
    SAFETY = "safety"
    PRESENTATION = "presentation"
    RELEVANCE = "relevance"


@dataclass
class QualityCheck:
    """Result of a single quality check."""
    stage: QualityStage
    passed: bool
    score: float  # 0.0 - 1.0
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


@dataclass
class QualityReport:
    """Full quality assessment report."""
    output: str
    overall_score: float
    level: QualityLevel
    checks: list[QualityCheck] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    correction_needed: bool = False
    correction_prompt: str = ""

    @property
    def passed(self) -> bool:
        return self.level not in (QualityLevel.POOR, QualityLevel.REJECTED)


class QualityGate:
    """Multi-stage output quality validation.

    Each stage validates a different aspect of the output. The gate
    can be configured with custom thresholds and rules.
    """

    def __init__(
        self,
        *,
        min_score: float = 0.6,
        min_correctness: float = 0.5,
        min_completeness: float = 0.4,
        min_safety: float = 0.9,
        min_presentation: float = 0.3,
        min_relevance: float = 0.5,
        max_output_length: int = 50000,
    ) -> None:
        self._min_score = min_score
        self._thresholds = {
            QualityStage.CORRECTNESS: min_correctness,
            QualityStage.COMPLETENESS: min_completeness,
            QualityStage.SAFETY: min_safety,
            QualityStage.PRESENTATION: min_presentation,
            QualityStage.RELEVANCE: min_relevance,
        }
        self._max_output_length = max_output_length
        self._metrics: dict[str, int] = defaultdict(int)

    async def validate(
        self,
        output: str,
        *,
        task: str = "",
        context: str = "",
        available_tools: list[str] | None = None,
    ) -> QualityReport:
        """Validate output through all quality stages.

        Args:
            output: The agent output to validate.
            task: The original task prompt.
            context: Additional context.
            available_tools: Tools that were available.

        Returns:
            QualityReport with full assessment.
        """
        checks: list[QualityCheck] = []

        # Stage 1: Correctness
        correctness = self._check_correctness(output, task, context)
        checks.append(correctness)

        # Stage 2: Completeness
        completeness = self._check_completeness(output, task)
        checks.append(completeness)

        # Stage 3: Safety
        safety = self._check_safety(output)
        checks.append(safety)

        # Stage 4: Presentation
        presentation = self._check_presentation(output)
        checks.append(presentation)

        # Stage 5: Relevance
        relevance = self._check_relevance(output, task)
        checks.append(relevance)

        # Calculate overall score
        scores = [c.score for c in checks]
        overall = sum(scores) / len(scores) if scores else 0.0

        # Determine level
        level = self._determine_level(overall, checks)

        # Check if correction is needed
        correction_needed = level in (QualityLevel.POOR, QualityLevel.REJECTED)
        correction_prompt = ""
        if correction_needed:
            correction_prompt = self._build_correction_prompt(output, checks, task)

        self._metrics["validated"] += 1
        if correction_needed:
            self._metrics["corrections_needed"] += 1

        return QualityReport(
            output=output,
            overall_score=overall,
            level=level,
            checks=checks,
            correction_needed=correction_needed,
            correction_prompt=correction_prompt,
        )

    def _check_correctness(self, output: str, task: str, context: str) -> QualityCheck:
        """Check factual correctness and logical consistency."""
        issues = []
        suggestions = []
        score = 1.0

        # Check for common error patterns
        error_patterns = [
            (r"\bI cannot\b|\bI can't\b|\bunable to\b", "Hedging language detected"),
            (r"\bTODO\b|\bFIXME\b|\bXXX\b", "Incomplete markers found"),
            (r"\{\{.*?\}\}|\[\[.*?\]\]", "Template placeholders left unfilled"),
            (r"\bError\b.*\boccurred\b", "Error mentioned in output"),
            (r"\bNone\b|\bnull\b|\bundefined\b", "Null values in output"),
        ]
        for pattern, desc in error_patterns:
            if re.search(pattern, output, re.IGNORECASE):
                issues.append(desc)
                score -= 0.15

        # Check for self-contradictions (simple)
        sentences = re.split(r"[.!?]", output)
        if len(sentences) > 3:
            # Check for repeated contradictory statements
            seen = set()
            for s in sentences:
                s_clean = s.strip().lower()[:50]
                if s_clean in seen and len(s_clean) > 10:
                    issues.append("Possible self-contradiction detected")
                    score -= 0.1
                    break
                seen.add(s_clean)

        # Check for hallucination indicators
        hallucination_patterns = [
            r"\bAs an AI\b",
            r"\bI don't have access\b",
            r"\bI cannot browse\b",
            r"\bmy training data\b",
        ]
        for pattern in hallucination_patterns:
            if re.search(pattern, output, re.IGNORECASE):
                issues.append("Hallucination indicator found")
                score -= 0.2
                break

        score = max(0.0, score)
        return QualityCheck(
            stage=QualityStage.CORRECTNESS,
            passed=score >= self._thresholds[QualityStage.CORRECTNESS],
            score=score,
            issues=issues,
            suggestions=suggestions,
        )

    def _check_completeness(self, output: str, task: str) -> QualityCheck:
        """Check if the output fully addresses the task."""
        issues = []
        suggestions = []
        score = 1.0

        # Check output length relative to task
        task_words = len(task.split())
        output_words = len(output.split())
        if task_words > 10 and output_words < task_words * 0.5:
            issues.append("Output seems too short for the task")
            score -= 0.3

        # Check for incomplete sections
        if re.search(r"\b(incomplete|partial|truncated|...)\b", output, re.IGNORECASE):
            issues.append("Output appears truncated")
            score -= 0.2

        # Check for unanswered questions in task
        questions = re.findall(r"\?", task)
        if len(questions) > 0:
            # Simple heuristic: check if output has corresponding statements
            answer_indicators = len(re.findall(r"\b(is|are|was|were|will|would|could|should)\b", output, re.IGNORECASE))
            if answer_indicators < len(questions):
                issues.append(f"Task has {len(questions)} questions but output may not answer all")
                score -= 0.15

        # Check for code completeness
        if "```" in output:
            code_blocks = output.count("```")
            if code_blocks % 2 != 0:
                issues.append("Unclosed code block detected")
                score -= 0.25

        score = max(0.0, score)
        return QualityCheck(
            stage=QualityStage.COMPLETENESS,
            passed=score >= self._thresholds[QualityStage.COMPLETENESS],
            score=score,
            issues=issues,
            suggestions=suggestions,
        )

    def _check_safety(self, output: str) -> QualityCheck:
        """Check for safety concerns."""
        issues = []
        suggestions = []
        score = 1.0

        # Check for dangerous patterns
        dangerous_patterns = [
            (r"\brm\s+-rf\b", "Dangerous rm command"),
            (r"\bDROP\s+TABLE\b", "Destructive SQL"),
            (r"\bformat\s+[a-z]:\b", "Disk format command"),
            (r"\b:(){ :|:& };:\b", "Fork bomb"),
            (r"\bchmod\s+777\b", "Overly permissive chmod"),
            (r"\bcurl\b.*\|\s*bash\b", "Pipe to shell"),
            (r"\bwget\b.*\|\s*bash\b", "Pipe to shell"),
        ]
        for pattern, desc in dangerous_patterns:
            if re.search(pattern, output, re.IGNORECASE):
                issues.append(f"Safety concern: {desc}")
                score -= 0.3

        # Check for credential exposure
        cred_patterns = [
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",  # email
            r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",  # credit card
            r"\b[A-Z0-9]{32,}\b",  # API key-like
        ]
        for pattern in cred_patterns:
            if re.search(pattern, output):
                issues.append("Possible credential exposure")
                score -= 0.4
                break

        score = max(0.0, score)
        return QualityCheck(
            stage=QualityStage.SAFETY,
            passed=score >= self._thresholds[QualityStage.SAFETY],
            score=score,
            issues=issues,
            suggestions=suggestions,
        )

    def _check_presentation(self, output: str) -> QualityCheck:
        """Check output formatting and presentation."""
        issues = []
        suggestions = []
        score = 1.0

        # Check length
        if len(output) > self._max_output_length:
            issues.append("Output exceeds maximum length")
            score -= 0.2

        # Check for excessive whitespace
        if re.search(r"\n{4,}", output):
            issues.append("Excessive blank lines")
            score -= 0.1

        # Check for proper markdown structure
        if "#" in output:
            headers = re.findall(r"^#{1,6}\s+", output, re.MULTILINE)
            if len(headers) > 20:
                issues.append("Excessive headers")
                score -= 0.1

        # Check for balanced formatting
        for char in ["*", "_", "`"]:
            count = output.count(char)
            if count % 2 != 0 and count > 2:
                issues.append(f"Unbalanced '{char}' formatting")
                score -= 0.05
                break

        score = max(0.0, score)
        return QualityCheck(
            stage=QualityStage.PRESENTATION,
            passed=score >= self._thresholds[QualityStage.PRESENTATION],
            score=score,
            issues=issues,
            suggestions=suggestions,
        )

    def _check_relevance(self, output: str, task: str) -> QualityCheck:
        """Check if output is relevant to the task."""
        issues = []
        suggestions = []
        score = 1.0

        # Simple keyword overlap check
        task_words = set(re.findall(r"\b\w+\b", task.lower()))
        output_words = set(re.findall(r"\b\w+\b", output.lower()))
        if task_words and output_words:
            overlap = len(task_words & output_words) / len(task_words)
            if overlap < 0.1:
                issues.append("Low keyword overlap with task")
                score -= 0.3
            elif overlap < 0.2:
                issues.append("Moderate keyword overlap with task")
                score -= 0.1

        # Check for off-topic indicators
        off_topic = ["I cannot help with", "I must decline", "against my guidelines"]
        for phrase in off_topic:
            if phrase.lower() in output.lower():
                issues.append("Output appears to decline the task")
                score -= 0.4
                break

        score = max(0.0, score)
        return QualityCheck(
            stage=QualityStage.RELEVANCE,
            passed=score >= self._thresholds[QualityStage.RELEVANCE],
            score=score,
            issues=issues,
            suggestions=suggestions,
        )

    def _determine_level(self, overall: float, checks: list[QualityCheck]) -> QualityLevel:
        """Determine overall quality level."""
        # Safety failure is automatic rejection
        safety = next((c for c in checks if c.stage == QualityStage.SAFETY), None)
        if safety and not safety.passed:
            return QualityLevel.REJECTED

        if overall >= 0.9:
            return QualityLevel.EXCELLENT
        elif overall >= 0.75:
            return QualityLevel.GOOD
        elif overall >= self._min_score:
            return QualityLevel.ACCEPTABLE
        else:
            return QualityLevel.POOR

    def _build_correction_prompt(self, output: str, checks: list[QualityCheck], task: str) -> str:
        """Build a prompt for correcting the output."""
        issues = []
        for check in checks:
            if not check.passed:
                issues.extend(check.issues)

        issue_text = "\n".join(f"- {i}" for i in issues[:5])
        return f"""The previous output had quality issues that need correction:

{issue_text}

Original task: {task}

Previous output (first 500 chars): {output[:500]}

Please provide a corrected version that addresses these issues."""

    def get_metrics(self) -> dict[str, Any]:
        return dict(self._metrics)
