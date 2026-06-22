"""Scan the Codex data directory (~/.codex/) to discover and index all conversations."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .models import Conversation
from .parser import extract_title, parse_session_file


def _parse_history(history_path: Path) -> dict[str, dict]:
    """Parse history.jsonl to build session index.

    Returns a dict mapping session_id -> {first_msg, last_ts, msg_count}.
    """
    sessions: dict[str, dict] = {}

    if not history_path.is_file():
        return sessions

    try:
        for line in history_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            sid = obj.get("session_id", "")
            ts = obj.get("ts", 0)
            text = obj.get("text", "")

            if sid not in sessions:
                sessions[sid] = {
                    "first_msg": text,
                    "last_ts": ts,
                    "msg_count": 0,
                }
            sessions[sid]["msg_count"] += 1
            # Track the latest timestamp
            if ts > sessions[sid]["last_ts"]:
                sessions[sid]["last_ts"] = ts
    except (OSError, UnicodeDecodeError):
        pass

    return sessions


def _find_session_file(sessions_dir: Path, session_id: str) -> Path | None:
    """Find the rollout JSONL file for a given session ID.

    Session files are named: rollout-YYYY-MM-DDTHH-MM-SS-<session_id>.jsonl
    stored under sessions/YYYY/MM/DD/
    """
    if not sessions_dir.is_dir():
        return None

    # Search all rollout files for one containing this session ID
    for jsonl_file in sessions_dir.rglob("rollout-*.jsonl"):
        if session_id in jsonl_file.name:
            return jsonl_file

    return None


def scan_conversations(base_dir: str | Path) -> list[Conversation]:
    """Scan the Codex data directory and return all discovered conversations.

    Args:
        base_dir: Path to ~/.codex/

    Returns:
        List of Conversation objects sorted by last_modified (newest first).
    """
    base = Path(base_dir)
    history_path = base / "history.jsonl"
    sessions_dir = base / "sessions"

    # Step 1: Build session index from history.jsonl
    session_index = _parse_history(history_path)

    if not session_index:
        return []

    results: list[Conversation] = []

    for sid, info in session_index.items():
        first_msg = info["first_msg"]
        last_ts = info["last_ts"]
        msg_count = info["msg_count"]

        # Derive title from first user message
        title = extract_title(first_msg)

        # Convert timestamp
        last_modified = datetime.fromtimestamp(last_ts, tz=timezone.utc)

        # Find the session rollout file
        session_file = _find_session_file(sessions_dir, sid)
        has_transcript = session_file is not None

        # Parse the session file for full transcript
        messages = []
        model = ""
        cwd = ""
        if session_file:
            meta, messages = parse_session_file(session_file)
            model = meta.get("model", "")
            cwd = meta.get("cwd", "")

        conv = Conversation(
            id=sid,
            title=title,
            last_modified=last_modified,
            messages=messages,
            has_transcript=has_transcript,
            session_file=str(session_file) if session_file else "",
            model=model,
            cwd=cwd,
            msg_count_from_history=msg_count,
        )
        results.append(conv)

    # Sort by last_modified descending (newest first)
    results.sort(key=lambda c: c.last_modified, reverse=True)
    return results
