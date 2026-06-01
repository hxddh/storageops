"""Prompt building and token-aware context management.

Builds prompts for the LLM, tracks token usage, and provides compaction
(summarization of older turns) when the context window gets full.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from storageops.core.event import UserMessage, AssistantMessage, SessionMeta
from storageops.core.session import Session


# ── Identity prompt (kept minimal — Pi handles tools/skills natively) ─

_IDENTITY = """You are StorageOps, an expert diagnostic agent for S3-compatible object storage
(AWS S3, Alibaba Cloud OSS, Tencent Cloud COS, Baidu BOS, Huawei OBS, MinIO, etc.).

## Capabilities
You have access to StorageOps diagnostic tools — parsers, analyzers, and detectors
for logs, error messages, policies, network traces, and cost attribution.
Pi discovers these tools automatically; call them by name.

## Safety Rules (non-negotiable)
1. **Offline only** — never connect to cloud APIs.
2. **Read-only** — label any mutating command with `# manual-only:`.
3. **Secret-safe** — redact all credentials, tokens, and signed URLs as [REDACTED].
4. **No destruction** — never recommend deleting data, disabling encryption,
   making buckets public, or bypassing IAM/KMS.
5. **Evidence-based** — every conclusion must cite tool output, not raw text.

## Workflow
1. Read evidence → identify tool(s) to call
2. Call tools → analyze results
3. Form and validate hypotheses
4. Report findings with confidence level

## Output
Start your final response with a YAML frontmatter block:
```
---
category: <domain>
root_cause_type: <snake_case>
confidence: <0.0–1.0>
severity: <critical|high|medium|low>
---
```
Then include: Summary, Key Evidence, Root Cause Ranking, Remediation, Safety Notes.

Be conversational. If the user is just chatting, respond naturally.
Only use diagnostic tools when evidence is provided."""


# ── Context manager ──────────────────────────────────────────────────

class ContextManager:
    """Tracks approximate token usage and compacts when needed."""

    def __init__(self, max_tokens: int = 120000) -> None:
        self.max_tokens = max_tokens
        self._turns_token_count: list[int] = []  # per-turn token estimates

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Very rough token estimate: ~4 chars per token."""
        return max(1, len(text) // 4)

    @staticmethod
    def count_tokens(events: list[Any]) -> int:
        """Estimate total tokens from session events."""
        total = 0
        for e in events:
            if hasattr(e, "text") and isinstance(e.text, str):
                total += ContextManager.estimate_tokens(e.text)
            if hasattr(e, "summary") and isinstance(e.summary, str):
                total += ContextManager.estimate_tokens(e.summary)
        return total

    def should_compact(self, session: Session | None) -> bool:
        """Return True if the context is approaching the limit."""
        if session is None or not session.events:
            return False
        est = self.count_tokens(session.events)
        return est > self.max_tokens * 0.7

    def compact_prompt(self, session: Session) -> str:
        """Build a compact summary of older turns to save tokens.

        Keeps the full identity, the most recent 2 turns in full,
        and summarizes older turns.
        """
        events = session.events
        users = [e for e in events if isinstance(e, UserMessage)]
        assistants = [e for e in events if isinstance(e, AssistantMessage)]

        if len(users) <= 3:
            # Not enough history to need compaction
            return build_prompt(session, users[-1].text if users else "", {})

        # Split: most recent 2 turns in full, older turns summarized
        recent_users = users[-2:]
        recent_assistants = assistants[-2:]
        older_users = users[:-2]
        older_assistants = assistants[:-2]

        summary_lines = ["## Earlier conversation (summarized)"]
        for u, a in zip(older_users, older_assistants):
            q = u.text[:200].replace("\n", " ")
            a_text = a.text[:300].replace("\n", " ")
            a_text = a_text.split("---", 2)[-1] if "---" in a_text else a_text
            summary_lines.append(f"- Q: {q}")
            summary_lines.append(f"  A: {a_text}")
        summary = "\n".join(summary_lines)

        recent_lines = ["## Recent conversation"]
        for u, a in zip(recent_users, recent_assistants):
            recent_lines.append(f"User: {u.text}")
            recent_lines.append(f"Assistant: {a.text}")

        # Last user message
        last_msg = users[-1].text if users else ""
        recent_lines.append(f"User: {last_msg}")

        full = f"{_IDENTITY}\n\n{summary}\n\n" + "\n\n".join(recent_lines)
        return full


# ── Prompt builder ───────────────────────────────────────────────────

def build_prompt(
    session: Session | None,
    user_input: str,
    extra: dict[str, str] | None = None,
) -> str:
    """Build the full prompt to send to the LLM.

    Args:
        session: The current session (for conversation history).
        user_input: The current user message.
        extra: Optional extra context (evidence file path, redaction count, etc.).

    Returns:
        A string prompt with identity, conversation history, and current input.
    """
    extra = extra or {}
    parts: list[str] = [_IDENTITY]

    # Add evidence context if provided
    if extra.get("evidence_file"):
        parts.append("")
        parts.append(f"## Evidence File")
        parts.append(f"Redacted evidence: {extra['evidence_file']}")
        if extra.get("original_filename"):
            parts.append(f"Original filename: {extra['original_filename']}")
        if extra.get("redaction_count"):
            parts.append(f"Redactions: {extra['redaction_count']} secret(s) replaced")

    # Add conversation history from session
    if session and session.needs_new_turn:
        history = session.build_replay_prompt()
        if history:
            parts.append("")
            parts.append("## Previous Conversation")
            parts.append(history)

    # Add current user input (already included in history above? handle carefully)
    already_in_history = False
    if session:
        for evt in reversed(session.events):
            if isinstance(evt, UserMessage) and evt.text.strip() == user_input.strip():
                already_in_history = True
                break

    if not already_in_history:
        parts.append("")
        parts.append(f"## Current Request")
        parts.append(user_input)

    return "\n".join(parts)


def load_identity_prompt() -> str:
    """Load the identity prompt from the prompts directory."""
    prompt_dir = Path(__file__).resolve().parents[1] / "prompts"
    path = prompt_dir / "identity.md"
    if path.exists():
        content = path.read_text(encoding="utf-8")
        if content.strip():
            return content.strip()
    return _IDENTITY
