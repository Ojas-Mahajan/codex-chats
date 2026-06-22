"""Parse overview.txt JSON-lines into structured Message objects."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import Message, ToolCall


def parse_timestamp(ts: Optional[str]) -> Optional[datetime]:
    """Parse an ISO 8601 timestamp string into a datetime."""
    if not ts:
        return None
    try:
        # Handle "2026-05-04T11:39:53Z" format
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def extract_user_request(content: str) -> str:
    """Extract the clean text from a <USER_REQUEST> block."""
    match = re.search(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", content, re.DOTALL)
    if match:
        return match.group(1).strip()
    return content.strip()


def extract_title_from_content(content: str, max_length: int = 60) -> str:
    """Derive a conversation title from the first user message content."""
    text = extract_user_request(content)

    # Remove markdown, URLs, and excessive whitespace
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[#*`\[\]]", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return "Untitled"

    # Take the first meaningful line
    first_line = text.split("\n")[0].strip()
    if len(first_line) > max_length:
        first_line = first_line[:max_length].rsplit(" ", 1)[0] + "…"

    return first_line if first_line else "Untitled"


def parse_tool_calls(raw_calls: list[dict]) -> list[ToolCall]:
    """Parse raw tool call dictionaries into ToolCall objects."""
    calls = []
    for tc in raw_calls:
        name = tc.get("name", "unknown")
        args = tc.get("args", {})
        # Clean up stringified args
        cleaned_args = {}
        for k, v in args.items():
            if isinstance(v, str):
                # Remove extra escaping from JSON strings
                try:
                    cleaned_args[k] = json.loads(v)
                except (json.JSONDecodeError, TypeError):
                    cleaned_args[k] = v
            else:
                cleaned_args[k] = v
        calls.append(ToolCall(name=name, args=cleaned_args))
    return calls


def clean_content(content: str) -> str:
    """Clean message content for display — remove XML wrapper tags."""
    if not content:
        return ""

    # Remove <USER_REQUEST> wrapper but keep content
    text = extract_user_request(content)

    # Remove <ADDITIONAL_METADATA> blocks entirely
    text = re.sub(
        r"<ADDITIONAL_METADATA>.*?</ADDITIONAL_METADATA>", "", text, flags=re.DOTALL
    )

    # Remove <USER_SETTINGS_CHANGE> blocks
    text = re.sub(
        r"<USER_SETTINGS_CHANGE>.*?</USER_SETTINGS_CHANGE>", "", text, flags=re.DOTALL
    )

    # Handle truncated markers
    text = re.sub(r"<truncated \d+ bytes>", "[…truncated…]", text)

    return text.strip()


def parse_overview(path: Path) -> list[Message]:
    """Parse an overview.txt JSON-lines file into a list of Message objects.

    Each line in overview.txt is a JSON object representing one step in
    the conversation.
    """
    messages = []

    try:
        raw_text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return messages

    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue

        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        # Parse the message fields
        step_index = obj.get("step_index", 0)
        source = obj.get("source", "UNKNOWN")
        msg_type = obj.get("type", "UNKNOWN")
        status = obj.get("status", "UNKNOWN")
        created_at = parse_timestamp(obj.get("created_at"))
        content = obj.get("content")

        # Parse tool calls if present
        tool_calls = []
        if "tool_calls" in obj:
            tool_calls = parse_tool_calls(obj["tool_calls"])

        # Clean content for display
        display_content = clean_content(content) if content else None

        msg = Message(
            step_index=step_index,
            source=source,
            type=msg_type,
            status=status,
            created_at=created_at,
            content=display_content,
            tool_calls=tool_calls,
        )
        messages.append(msg)

    return messages


def derive_title(messages: list[Message]) -> str:
    """Derive a conversation title from the first user message."""
    for msg in messages:
        if msg.source == "USER_EXPLICIT" and msg.type == "USER_INPUT" and msg.content:
            return extract_title_from_content(msg.content)
    return "Untitled"
