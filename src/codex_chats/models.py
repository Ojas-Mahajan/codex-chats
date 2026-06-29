"""Data models for Codex conversations and messages."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


@dataclass
class ToolCall:
    """A single tool/function call made by the model."""

    name: str
    args: dict = field(default_factory=dict)


@dataclass
class Message:
    """A single message within a conversation."""

    index: int
    role: str  # "user", "assistant", "developer", "system"
    content: str = ""
    timestamp: Optional[datetime] = None
    msg_type: str = ""  # "message", "reasoning", "function_call", etc.
    tool_calls: list[ToolCall] = field(default_factory=list)

    @property
    def role_icon(self) -> str:
        """Return an icon representing the message role."""
        icons = {
            "user": "👤",
            "assistant": "🤖",
            "developer": "⚙️",
            "system": "⚙️",
        }
        return icons.get(self.role, "❓")

    @property
    def role_label(self) -> str:
        """Return a human-readable label for the message role."""
        return self.role.upper()

    @property
    def display_type(self) -> str:
        """Return a human-readable message type."""
        type_map = {
            "message": "Message",
            "reasoning": "Thinking",
            "function_call": "Tool Call",
            "function_call_output": "Tool Output",
        }
        return type_map.get(self.msg_type, self.msg_type.replace("_", " ").title())


@dataclass
class Conversation:
    """A single Codex conversation with its metadata and messages."""

    id: str
    title: str
    last_modified: datetime
    started_at: Optional[datetime] = None
    activity_dates: tuple[date, ...] = field(default_factory=tuple)
    messages: list[Message] = field(default_factory=list)
    has_transcript: bool = False
    session_file: str = ""
    model: str = ""
    cwd: str = ""
    msg_count_from_history: int = 0
    transcript_loaded: bool = False

    @property
    def local_last_modified(self) -> datetime:
        """Return the last modified timestamp in the user's local timezone."""
        if self.last_modified.tzinfo:
            return self.last_modified.astimezone()
        return self.last_modified

    @property
    def local_started_at(self) -> Optional[datetime]:
        """Return the start timestamp in the user's local timezone."""
        if self.started_at and self.started_at.tzinfo:
            return self.started_at.astimezone()
        return self.started_at

    @property
    def date_label(self) -> str:
        """Return a short date label like 'Jun 22'."""
        return self.local_last_modified.strftime("%b %d")

    @property
    def message_count(self) -> int:
        """Return the number of user/assistant messages with content."""
        return sum(
            1
            for m in self.messages
            if m.role in ("user", "assistant") and m.content
        )
