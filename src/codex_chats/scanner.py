"""Scan the Codex data directory (~/.codex/) to discover and index conversations."""

from __future__ import annotations

import json
import math
import os
import stat
import tempfile
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


def _valid_history_timestamp(value: object) -> float | None:
    """Return a usable POSIX timestamp, or ``None`` for a malformed value."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None

    timestamp = float(value)
    if not math.isfinite(timestamp):
        return None

    try:
        datetime.fromtimestamp(timestamp, tz=timezone.utc)
    except (OSError, OverflowError, ValueError):
        return None
    return timestamp


def _parse_history(history_path: Path) -> dict[str, dict]:
    """Parse history.jsonl to build session index.

    Returns a dict mapping session_id -> metadata gathered from history rows.
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

                if not isinstance(obj, dict):
                    continue

                sid = obj.get("session_id")
                ts = _valid_history_timestamp(obj.get("ts"))
                if not isinstance(sid, str) or not sid or ts is None:
                    continue

                text = obj.get("text", "")
                if not isinstance(text, str):
                    text = ""

                if sid not in sessions:
                    sessions[sid] = {
                        "first_msg": text,
                        "first_ts": ts,
                        "last_ts": ts,
                        "msg_count": 0,
                        "activity_ts": set(),
                    }
                sessions[sid]["msg_count"] += 1
                sessions[sid]["activity_ts"].add(ts)
                if ts < sessions[sid]["first_ts"]:
                    sessions[sid]["first_ts"] = ts
                    sessions[sid]["first_msg"] = text
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
        # Do not follow an unexpected symlink outside the Codex sessions tree.
        if jsonl_file.is_symlink():
            continue
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
        first_ts = info["first_ts"]
        last_ts = info["last_ts"]
        msg_count = info["msg_count"]
        activity_dates = tuple(
            sorted(
                {
                    datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().date()
                    for ts in info["activity_ts"]
                },
                reverse=True,
            )
        )

        # Derive title from first user message
        title = extract_title(first_msg)

        # Convert timestamp
        started_at = datetime.fromtimestamp(first_ts, tz=timezone.utc)
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
            started_at = meta.get("started_at", started_at)

        conv = Conversation(
            id=sid,
            title=title,
            last_modified=last_modified,
            started_at=started_at,
            activity_dates=activity_dates,
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


def _filter_history_rows(data: bytes, sid: str) -> tuple[bytes, int]:
    """Return history content without rows for ``sid``.

    Invalid JSON and non-object JSON values are retained byte-for-byte. Deletion
    should not turn a recoverable bad history row into data loss.
    """
    retained: list[bytes] = []
    removed_rows = 0

    for line in data.splitlines(keepends=True):
        if not line.strip():
            retained.append(line)
            continue

        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            retained.append(line)
            continue

        if isinstance(obj, dict) and obj.get("session_id") == sid:
            removed_rows += 1
        else:
            retained.append(line)

    return b"".join(retained), removed_rows


def _write_private_temp_file(directory: Path, filename: str, data: bytes) -> Path:
    """Write ``data`` to a unique owner-only temporary file in ``directory``."""
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{filename}.",
        suffix=".tmp",
        dir=directory,
    )
    temp_path = Path(temp_name)
    try:
        # mkstemp uses this mode on POSIX, but set it explicitly so a changed
        # process umask cannot expose prompt text before the atomic rename.
        if hasattr(os, "fchmod"):
            os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(fd, "wb") as target:
            fd = -1
            target.write(data)
            target.flush()
            os.fsync(target.fileno())
    except BaseException:
        if fd != -1:
            os.close(fd)
        temp_path.unlink(missing_ok=True)
        raise
    return temp_path


def _link_history_snapshot(history_path: Path) -> Path:
    """Create a private hard link to the current history inode.

    The link lets us recover rows written through a file descriptor that was
    opened before ``history.jsonl`` was atomically replaced. It is removed as
    soon as those rows have been merged into the new history file.
    """
    for _ in range(10):
        fd, link_name = tempfile.mkstemp(
            prefix=f".{history_path.name}.",
            suffix=".snapshot",
            dir=history_path.parent,
        )
        link_path = Path(link_name)
        os.close(fd)
        link_path.unlink()
        try:
            os.link(history_path, link_path)
        except FileExistsError:
            continue
        except OSError:
            # Hard links are available on the supported platforms. Do not
            # silently fall back to the old replacement race if the filesystem
            # rejects one, because preserving prompts is more important.
            raise
        return link_path

    raise OSError("could not allocate a private history snapshot link")


def _append_history_rows(history_path: Path, data: bytes) -> None:
    """Append recovered rows without overwriting a concurrent new writer."""
    if not data:
        return

    fd = os.open(history_path, os.O_WRONLY | os.O_APPEND)
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def _rewrite_history_without_session(history_path: Path, sid: str) -> int:
    """Safely remove one session's rows while preserving concurrent appends.

    Codex appends to history.jsonl independently of this program. Before an
    atomic replacement we compare the file with the snapshot used to prepare
    the replacement. A changed file is rebuilt from a fresh snapshot instead
    of being overwritten. If it remains busy, fail safely rather than risk
    discarding a newly-written prompt.
    """
    max_attempts = 5
    for _ in range(max_attempts):
        try:
            history_mode = history_path.lstat().st_mode
            if not stat.S_ISREG(history_mode):
                raise OSError("refusing to rewrite a non-regular history.jsonl file")
            # An existing history file might have been created by an older
            # version with the process umask. Restrict it before reading it.
            os.chmod(history_path, stat.S_IRUSR | stat.S_IWUSR)
            snapshot = history_path.read_bytes()
        except FileNotFoundError:
            return 0

        rewritten, removed_rows = _filter_history_rows(snapshot, sid)
        snapshot_link = _link_history_snapshot(history_path)
        temp_path = _write_private_temp_file(
            history_path.parent,
            history_path.name,
            rewritten,
        )
        try:
            try:
                current = history_path.read_bytes()
            except FileNotFoundError:
                # A concurrent writer replaced the file; retry against its
                # current contents rather than resurrecting an old snapshot.
                continue

            if current != snapshot:
                continue

            os.replace(temp_path, history_path)
            # A writer that had history.jsonl open before os.replace writes to
            # the old inode. The hard link retains that inode long enough to
            # merge its appended rows into the new, private history file.
            old_inode_content = snapshot_link.read_bytes()
            if old_inode_content.startswith(snapshot):
                concurrent_rows, concurrent_removed = _filter_history_rows(
                    old_inode_content[len(snapshot) :], sid
                )
                _append_history_rows(history_path, concurrent_rows)
                return removed_rows + concurrent_removed

            # The final path comparison above already rejected in-place edits
            # before replacement. A non-append mutation here can only target a
            # stale, pre-replacement descriptor, so it cannot affect the new
            # history file and must not turn an otherwise committed deletion
            # into a partial failure.
            return removed_rows
        finally:
            temp_path.unlink(missing_ok=True)
            snapshot_link.unlink(missing_ok=True)

    raise OSError(
        "history.jsonl changed repeatedly while deleting the session; "
        "nothing was deleted"
    )


def _session_file_within_root(session_file: Path, sessions_root: Path) -> bool:
    """Return whether a rollout path resolves inside the expected sessions tree."""
    try:
        session_file.resolve(strict=False).relative_to(sessions_root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _stage_rollout_for_deletion(
    session_file: str, sessions_root: Path
) -> tuple[Path, Path] | None:
    """Move a rollout file to a private staging name until history is updated."""
    if not session_file:
        return None

    original = Path(session_file)
    if not _session_file_within_root(original, sessions_root):
        raise OSError("refusing to delete a rollout file outside the sessions directory")

    try:
        original.lstat()
    except FileNotFoundError:
        return None

    fd, staged_name = tempfile.mkstemp(
        prefix=".codex-chats-delete-",
        suffix=".jsonl",
        dir=original.parent,
    )
    staged = Path(staged_name)
    try:
        os.close(fd)
        fd = -1
        # Rename is reversible and cannot follow a symlink at the staging
        # destination. It keeps the transcript recoverable if history update
        # fails after this point.
        os.replace(original, staged)
    except BaseException:
        if fd != -1:
            os.close(fd)
        staged.unlink(missing_ok=True)
        raise
    return original, staged


def _restore_staged_rollout(original: Path, staged: Path) -> None:
    """Put a staged rollout back after a failed history rewrite."""
    try:
        os.replace(staged, original)
    except OSError as exc:
        raise OSError(
            f"history update failed and the rollout could not be restored; "
            f"it remains at {staged}"
        ) from exc


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

    # Move the rollout aside instead of unlinking it immediately. If a history
    # rewrite fails, the transcript can be put back exactly where it was.
    staged_rollout = _stage_rollout_for_deletion(session_file, base / "sessions")

    # Rewrite history first. The private temporary file is atomically renamed
    # into place only when its source snapshot is still current.
    history_path = base / "history.jsonl"
    try:
        if history_path.is_file():
            removed_history_rows = _rewrite_history_without_session(history_path, sid)
    except BaseException:
        if staged_rollout:
            original, staged = staged_rollout
            _restore_staged_rollout(original, staged)
        raise

    # History is now committed, so the staged transcript can be permanently
    # removed. A successful rename has already proved permission to unlink in
    # its containing directory under normal filesystem semantics.
    if staged_rollout:
        original, staged = staged_rollout
        try:
            staged.unlink()
        except OSError as exc:
            # The transcript is still intact at the private staged path. Try
            # to restore it so a cleanup failure never silently destroys it.
            try:
                _restore_staged_rollout(original, staged)
            except OSError as restore_exc:
                raise restore_exc from exc
            raise
        deleted_rollout_file = True
        _prune_empty_session_dirs(original.parent, base / "sessions")

    return DeleteSessionResult(
        deleted_rollout_file=deleted_rollout_file,
        removed_history_rows=removed_history_rows,
    )
