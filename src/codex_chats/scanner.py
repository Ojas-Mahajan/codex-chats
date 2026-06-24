g"""Scan the Codex data directory (~/.codex/) to discover and index all conversations."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .models import Conversation
from .parser import extract_title, parse_session_metadata


@dataclass(frozen=True)
class DeleteSessionResult:
    """Details about a deleted session."""

    deleted_rollout_file: bool
    removed_history_rows: int


def _parse_history(history_path: Path) -> dict[str, dict]:
    """Parse history.jsonl to build session index.

    Returns a dict mapping session_id -> {first_msg, last_ts, msg_count}.
    """
    sessions: dict[str, dict] = {}

    if not history_path.is_file():
        return sessions

    try:
        with history_path.open("r", encoding="utf-8") as lines:
            for line in lines:
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


def _extract_session_id_from_rollout(path: Path) -> str:
    """Extract the session ID suffix from a rollout filename."""
    name = path.name
    prefix = "rollout-"
    suffix = ".jsonl"
    if not name.startswith(prefix) or not name.endswith(suffix):
        return ""

    stem = name.removesuffix(suffix)
    # rollout-YYYY-MM-DDTHH-MM-SS-<session_id>
    timestamp_parts = 5
    parts = stem.removeprefix(prefix).split("-", timestamp_parts)
    if len(parts) <= timestamp_parts:
        return ""
    return parts[-1]


def _build_session_file_index(sessions_dir: Path) -> dict[str, Path]:
    """Build a single-pass index of session ID to rollout JSONL path."""
    index: dict[str, Path] = {}

    if not sessions_dir.is_dir():
        return index

    for jsonl_file in sessions_dir.rglob("rollout-*.jsonl"):
        session_id = _extract_session_id_from_rollout(jsonl_file)
        if session_id:
            index[session_id] = jsonl_file
    return index


def _find_session_file(
    sessions_dir: Path, session_id: str, file_index: dict[str, Path] | None = None
) -> Path | None:
    """Find the rollout JSONL file for a given session ID.

    Session files are named: rollout-YYYY-MM-DDTHH-MM-SS-<session_id>.jsonl
    stored under sessions/YYYY/MM/DD/
    """
    if file_index is not None:
        return file_index.get(session_id)

    if not sessions_dir.is_dir():
        return None

    # Fallback for unexpected filename formats.
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

    session_files = _build_session_file_index(sessions_dir)
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
        session_file = _find_session_file(sessions_dir, sid, session_files)
        has_transcript = session_file is not None

        # Parse only lightweight metadata; transcripts are loaded on demand.
        model = ""
        cwd = ""
        if session_file:
            meta = parse_session_metadata(session_file)
            model = meta.get("model", "")
            cwd = meta.get("cwd", "")

        conv = Conversation(
            id=sid,
            title=title,
            last_modified=last_modified,
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


def _prune_empty_session_dirs(path: Path, sessions_root: Path) -> None:
    """Remove empty session directories up to, but not including, sessions_root."""
    try:
        sessions_root = sessions_root.resolve()
    except OSError:
        return

    current = path
    while current != sessions_root and sessions_root in current.parents:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def delete_session_data(
    base_dir: str | Path, sid: str, session_file: str
) -> DeleteSessionResult:
    """Delete a session's rollout file and remove it from history.jsonl.

    Raises:
        OSError: If a filesystem operation fails.
    """
    base = Path(base_dir)
    deleted_rollout_file = False
    removed_history_rows = 0

    # 1. Delete rollout file
    if session_file:
        sf = Path(session_file)
        if sf.is_file():
            sf.unlink()
            deleted_rollout_file = True
            _prune_empty_session_dirs(sf.parent, base / "sessions")

    # 2. Scrub from history.jsonl
    history_path = base / "history.jsonl"
    if history_path.is_file():
        tmp_path = history_path.with_name(f"{history_path.name}.tmp")
        try:
            with history_path.open("r", encoding="utf-8") as source, tmp_path.open(
                "w", encoding="utf-8"
            ) as target:
                for line in source:
                    stripped = line.strip()
                    if not stripped:
                        target.write(line)
                        continue
                    try:
                        obj = json.loads(line)
                        if obj.get("session_id") != sid:
                            target.write(line)
                        else:
                            removed_history_rows += 1
                    except json.JSONDecodeError:
                        target.write(line)
            os.replace(tmp_path, history_path)
        except OSError:
            tmp_path.unlink(missing_ok=True)
            raise

    return DeleteSessionResult(
        deleted_rollout_file=deleted_rollout_file,
        removed_history_rows=removed_history_rows,
    )
