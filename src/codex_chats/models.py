"""Data models for Antigravity conversations and messages."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ToolCall:
    """A single tool/function call made by the model."""

    name: str
    args: dict = field(default_factory=dict)


@dataclass
class Message:
    """A single message within a conversation."""

    step_index: int
    source: str  # "USER_EXPLICIT", "MODEL", "USER_IMPLICIT" etc.
    type: str  # "USER_INPUT", "PLANNER_RESPONSE", "VIEW_FILE" etc.
    status: str
    created_at: Optional[datetime] = None
    content: Optional[str] = None
    tool_calls: list[ToolCall] = field(default_factory=list)

    @property
    def role_icon(self) -> str:
        """Return an icon representing the message source."""
        if self.source == "USER_EXPLICIT":
            return "👤"
        elif self.source == "MODEL":
            return "🤖"
        else:
            return "⚙️"

    @property
    def role_label(self) -> str:
        """Return a human-readable label for the message source."""
        if self.source == "USER_EXPLICIT":
            return "USER"
        elif self.source == "MODEL":
            return "MODEL"
        else:
            return "SYSTEM"

    @property
    def display_type(self) -> str:
        """Return a human-readable message type."""
        type_map = {
            "USER_INPUT": "Message",
            "PLANNER_RESPONSE": "Response",
            "VIEW_FILE": "View File",
            "TOOL_CALL": "Tool Call",
        }
        return type_map.get(self.type, self.type.replace("_", " ").title())


@dataclass
class Conversation:
    """A single Antigravity conversation with its metadata and messages."""

    id: str
    title: str
    last_modified: datetime
    messages: list[Message] = field(default_factory=list)
    has_logs: bool = False
    artifacts: list[str] = field(default_factory=list)
    size_bytes: int = 0

    @property
    def date_label(self) -> str:
        """Return a short date label like 'Jun 22'."""
        return self.last_modified.strftime("%b %d")

    @property
    def message_count(self) -> int:
        """Return the number of user/model messages (excluding system)."""
        return sum(
            1
            for m in self.messages
            if m.source in ("USER_EXPLICIT", "MODEL")
            and m.content  # Only count messages with actual content
        )

    @property
    def size_label(self) -> str:
        """Return a human-readable size label."""
        if self.size_bytes < 1024:
            return f"{self.size_bytes} B"
        elif self.size_bytes < 1024 * 1024:
            return f"{self.size_bytes / 1024:.0f} KB"
        else:
            return f"{self.size_bytes / (1024 * 1024):.1f} MB"
