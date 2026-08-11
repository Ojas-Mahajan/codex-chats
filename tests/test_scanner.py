from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from codex_chats import scanner


def _history_row(session_id: str, timestamp: int, text: str) -> str:
    return json.dumps({"session_id": session_id, "ts": timestamp, "text": text})


def _create_rollout(base_dir: Path, session_id: str) -> Path:
    rollout = (
        base_dir
        / "sessions"
        / "2026"
        / "08"
        / "11"
        / f"rollout-2026-08-11T12-00-00-{session_id}.jsonl"
    )
    rollout.parent.mkdir(parents=True)
    rollout.write_text('{"type":"session_meta","payload":{}}\n', encoding="utf-8")
    return rollout


def test_scan_skips_malformed_history_rows(tmp_path: Path) -> None:
    history = tmp_path / "history.jsonl"
    history.write_text(
        "\n".join(
            [
                _history_row("valid", 1_700_000_000, "A usable prompt"),
                json.dumps({"session_id": "missing-ts", "text": "bad"}),
                json.dumps({"session_id": "string-ts", "ts": "bad", "text": "bad"}),
                json.dumps({"session_id": "nan-ts", "ts": float("nan"), "text": "bad"}),
                json.dumps({"session_id": 42, "ts": 1_700_000_001, "text": "bad"}),
                json.dumps(["valid JSON, wrong shape"]),
                "{not valid json}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    conversations = scanner.scan_conversations(tmp_path)

    assert [conversation.id for conversation in conversations] == ["valid"]
    assert conversations[0].title == "A usable prompt"


def test_delete_uses_private_unique_temp_file(tmp_path: Path) -> None:
    history = tmp_path / "history.jsonl"
    history.write_text(
        _history_row("delete-me", 1_700_000_000, "private prompt") + "\n",
        encoding="utf-8",
    )
    rollout = _create_rollout(tmp_path, "delete-me")

    protected_file = tmp_path / "must-not-be-overwritten"
    protected_file.write_text("leave this alone", encoding="utf-8")
    fixed_temp_name = tmp_path / "history.jsonl.tmp"
    fixed_temp_name.symlink_to(protected_file)

    result = scanner.delete_session_data(tmp_path, "delete-me", str(rollout))

    assert result.removed_history_rows == 1
    assert protected_file.read_text(encoding="utf-8") == "leave this alone"
    assert stat.S_IMODE(history.stat().st_mode) == 0o600


def test_delete_retries_when_history_grows_during_rewrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    history = tmp_path / "history.jsonl"
    history.write_text(
        _history_row("delete-me", 1_700_000_000, "delete this") + "\n",
        encoding="utf-8",
    )
    rollout = _create_rollout(tmp_path, "delete-me")
    concurrent_row = _history_row("new-session", 1_700_000_001, "new prompt") + "\n"

    real_write_temp = scanner._write_private_temp_file
    writes = 0

    def write_temp_and_append(*args, **kwargs):
        nonlocal writes
        temp_path = real_write_temp(*args, **kwargs)
        if writes == 0:
            with history.open("a", encoding="utf-8") as source:
                source.write(concurrent_row)
        writes += 1
        return temp_path

    monkeypatch.setattr(scanner, "_write_private_temp_file", write_temp_and_append)

    scanner.delete_session_data(tmp_path, "delete-me", str(rollout))

    final_history = history.read_text(encoding="utf-8")
    assert "delete this" not in final_history
    assert concurrent_row in final_history


def test_history_rewrite_keeps_rows_from_a_preopened_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    history = tmp_path / "history.jsonl"
    history.write_text(
        _history_row("delete-me", 1_700_000_000, "delete this") + "\n",
        encoding="utf-8",
    )
    concurrent_row = _history_row("new-session", 1_700_000_001, "new prompt") + "\n"

    real_replace = scanner.os.replace
    old_history_writer = history.open("a", encoding="utf-8")

    def replace_after_old_writer(source, destination):
        if Path(destination) == history and Path(source).suffix == ".tmp":
            old_history_writer.write(concurrent_row)
            old_history_writer.flush()
        return real_replace(source, destination)

    monkeypatch.setattr(scanner.os, "replace", replace_after_old_writer)
    try:
        removed_rows = scanner._rewrite_history_without_session(history, "delete-me")
    finally:
        old_history_writer.close()

    final_history = history.read_text(encoding="utf-8")
    assert removed_rows == 1
    assert "delete this" not in final_history
    assert concurrent_row in final_history


def test_delete_restores_rollout_when_history_update_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    history = tmp_path / "history.jsonl"
    original_history = _history_row("delete-me", 1_700_000_000, "keep until commit") + "\n"
    history.write_text(original_history, encoding="utf-8")
    rollout = _create_rollout(tmp_path, "delete-me")

    def fail_rewrite(_history: Path, _sid: str) -> int:
        raise OSError("simulated history failure")

    monkeypatch.setattr(scanner, "_rewrite_history_without_session", fail_rewrite)

    with pytest.raises(OSError, match="simulated history failure"):
        scanner.delete_session_data(tmp_path, "delete-me", str(rollout))

    assert rollout.is_file()
    assert history.read_text(encoding="utf-8") == original_history
