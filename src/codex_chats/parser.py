"""Parse Codex session rollout JSONL files into structured Message objects."""

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
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def extract_title(text: str, max_length: int = 60) -> str:
    """Derive a conversation title from the first user message.

    Cleans up skill references, URLs, XML tags, and excessive whitespace.
    """
    if not text:
        return "Untitled"

    # Remove skill references like [$skill-name](path)
    text = re.sub(r"\[?\$[\w-]+\]?\([^)]*\)", "", text)
    # Remove URLs
    text = re.sub(r"https?://\S+", "", text)
    # Remove XML/HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Remove markdown formatting
    text = re.sub(r"[#*`\[\]]", "", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return "Untitled"

    # Take the first line
    first_line = text.split("\n")[0].strip()
    if len(first_line) > max_length:
        first_line = first_line[:max_length].rsplit(" ", 1)[0] + "…"

    return first_line if first_line else "Untitled"


def extract_message_text(content_list: list) -> str:
    """Extract readable text from a Codex message content array.

    Content items can have types: input_text, output_text, refusal, etc.
    """
    parts = []
    for item in content_list:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type", "")
        if item_type in ("input_text", "output_text"):
            text = item.get("text", "")
            # Skip system/environment context blocks
            if text.startswith("<environment_context>"):
                continue
            if text.startswith("<permissions instructions>"):
                continue
            parts.append(text)
        elif item_type == "refusal":
            parts.append(f"[Refusal: {item.get('refusal', '')}]")
    return "\n".join(parts)


def parse_session_file(path: Path) -> tuple[dict, list[Message]]:
    """Parse a Codex session rollout JSONL file.

    Returns:
        A tuple of (session_meta_dict, list_of_messages).
    """
    meta = {}
    messages: list[Message] = []
    msg_index = 0

    try:
        lines = path.open("r", encoding="utf-8")
    except OSError:
        return meta, messages

    try:
        for line in lines:
            line = line.strip()
            if not line:
                continue

            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            entry_type = obj.get("type", "")
            timestamp = parse_timestamp(obj.get("timestamp"))
            payload = obj.get("payload", {})

            if entry_type == "session_meta":
                meta = payload
                continue

            if entry_type == "turn_context":
                # Extract model info from turn context
                if "model" in payload:
                    meta["model"] = payload["model"]
                continue

            if entry_type != "response_item":
                continue

            role = payload.get("role", "")
            msg_type = payload.get("type", "")

            # Skip non-message types we don't care about
            if msg_type not in (
                "message",
                "reasoning",
                "function_call",
                "function_call_output",
            ):
                continue

            # Extract content
            content = ""
            tool_calls = []

            if msg_type == "message":
                content_list = payload.get("content", [])
                if isinstance(content_list, list):
                    content = extract_message_text(content_list)
                elif isinstance(content_list, str):
                    content = content_list

            elif msg_type == "reasoning":
                # Reasoning/thinking content
                summary = payload.get("summary", [])
                if isinstance(summary, list):
                    parts = []
                    for s in summary:
                        if isinstance(s, dict):
                            parts.append(s.get("text", ""))
                        elif isinstance(s, str):
                            parts.append(s)
                    content = "\n".join(parts)
                elif isinstance(summary, str):
                    content = summary
                if not content:
                    content = "[thinking...]"

            elif msg_type == "function_call":
                name = payload.get("name", "unknown")
                args_str = payload.get("arguments", "{}")
                try:
                    args = json.loads(args_str) if isinstance(args_str, str) else args_str
                except json.JSONDecodeError:
                    args = {"raw": args_str}
                tool_calls.append(
                    ToolCall(
                        name=name,
                        args=args if isinstance(args, dict) else {"raw": str(args)},
                    )
                )
                content = f"🔧 {name}"

            elif msg_type == "function_call_output":
                output = payload.get("output", "")
                if isinstance(output, list):
                    parts = []
                    for item in output:
                        if isinstance(item, dict):
                            if item.get("type") == "input_image":
                                parts.append("[Image Output]")
                            else:
                                parts.append(str(item))
                        else:
                            parts.append(str(item))
                    output_str = "\n".join(parts)
                else:
                    output_str = str(output)
                content = output_str[:2000] if output_str else "[no output]"

            # Skip empty messages and developer/system context
            if not content and not tool_calls:
                continue
            if role == "developer":
                continue

            msg = Message(
                index=msg_index,
                role=role or "system",
                content=content,
                timestamp=timestamp,
                msg_type=msg_type,
                tool_calls=tool_calls,
            )
            messages.append(msg)
            msg_index += 1
    except UnicodeDecodeError:
        return meta, messages
    finally:
        lines.close()

    return meta, messages


def parse_session_metadata(path: Path) -> dict:
    """Parse only lightweight session metadata needed for list/search views."""
    meta = {}
    have_cwd = False
    have_model = False
    checked_started_at = False

    try:
        lines = path.open("r", encoding="utf-8")
    except OSError:
        return meta

    try:
        for line in lines:
            if have_cwd and have_model and checked_started_at:
                break

            line = line.strip()
            if not line:
                continue

            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            entry_type = obj.get("type", "")
            payload = obj.get("payload", {})

            if entry_type == "session_meta":
                cwd = payload.get("cwd")
                if cwd:
                    meta["cwd"] = cwd
                    have_cwd = True
                model = payload.get("model")
                if model:
                    meta["model"] = model
                    have_model = True
                started_at = parse_timestamp(
                    payload.get("timestamp") or obj.get("timestamp")
                )
                if started_at:
                    meta["started_at"] = started_at
                checked_started_at = True
                continue

            if entry_type == "turn_context":
                model = payload.get("model")
                if model:
                    meta["model"] = model
                    have_model = True
    except UnicodeDecodeError:
        return meta
    finally:
        lines.close()

    return meta
