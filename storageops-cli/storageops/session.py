"""Diagnostic session: accumulates evidence and conversation across turns."""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Turn:
    role: str   # "user" | "assistant"
    content: str


class DiagnosticSession:
    """Holds state for one interactive diagnostic conversation."""

    def __init__(self) -> None:
        self.turns: list[Turn] = []
        self.evidence_blocks: list[str] = []
        self.domain: str | None = None
        self.verbose: bool = False

    # ── Evidence ──────────────────────────────────────────────────────

    def add_evidence(self, text: str) -> None:
        t = text.strip()
        if t:
            self.evidence_blocks.append(t)

    @property
    def accumulated_evidence(self) -> str:
        return "\n\n---\n\n".join(self.evidence_blocks)

    def has_log_content(self, text: str) -> bool:
        """Heuristic: does this look like real log/error output worth running Pi on?"""
        indicators = [
            r'\b(Error|Exception|ERROR|WARN|DEBUG|FATAL|CRITICAL)\b',
            r'\b(AccessDenied|NoSuchKey|InvalidSignature|NoSuchBucket|403|404|500|503)\b',
            r'\b(s3://|arn:aws:|amazonaws\.com|SignatureDoesNotMatch)\b',
            r'(Traceback|stack trace|at com\.|at org\.|\tat )',
            r'"[Cc]ode"\s*:\s*"[A-Z]',
            r'<(Error|Code|Message)>',
            r'(time_total|time_connect|HTTP/\d)',
            r'(rclone v\d|s5cmd|aws-cli)',
        ]
        return any(re.search(p, text) for p in indicators)

    # ── Conversation ──────────────────────────────────────────────────

    def add_turn(self, role: str, content: str) -> None:
        self.turns.append(Turn(role=role, content=content))

    def reset(self) -> None:
        self.turns.clear()
        self.evidence_blocks.clear()
        self.domain = None
