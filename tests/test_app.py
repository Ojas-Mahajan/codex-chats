from __future__ import annotations

import asyncio
import json
from pathlib import Path

from codex_chats.app import CodexChatsApp


def _response(timestamp: str, role: str, content_type: str, text: str) -> str:
    return json.dumps(
        {
            "timestamp": timestamp,
            "type": "response_item",
            "payload": {
                "role": role,
                "type": "message",
                "content": [{"type": content_type, "text": text}],
            },
        }
    )


def test_reload_after_resume_replaces_cached_transcript(tmp_path: Path) -> None:
    async def exercise_app() -> None:
        rollout = (
            tmp_path
            / "sessions"
            / "2026"
            / "08"
            / "11"
            / "rollout-2026-08-11T12-00-00-test-session.jsonl"
        )
        rollout.parent.mkdir(parents=True)
        rollout.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "type": "session_meta",
                            "payload": {"cwd": str(tmp_path)},
                        }
                    ),
                    _response(
                        "2026-08-11T12:00:00Z",
                        "user",
                        "input_text",
                        "before resume",
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        history = tmp_path / "history.jsonl"
        history.write_text(
            json.dumps(
                {
                    "session_id": "test-session",
                    "ts": 1_786_449_600,
                    "text": "before resume",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        app = CodexChatsApp(tmp_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app._selected_conversation is not None
            assert [message.content for message in app._selected_conversation.messages] == [
                "before resume"
            ]

            with rollout.open("a", encoding="utf-8") as transcript:
                transcript.write(
                    _response(
                        "2026-08-11T12:01:00Z",
                        "assistant",
                        "output_text",
                        "after resume",
                    )
                    + "\n"
                )
            with history.open("a", encoding="utf-8") as rows:
                rows.write(
                    json.dumps(
                        {
                            "session_id": "test-session",
                            "ts": 1_786_449_660,
                            "text": "continued after resume",
                        }
                    )
                    + "\n"
                )

            app._reload_conversations(preferred_id="test-session")
            await pilot.pause()

            assert app._selected_conversation is not None
            assert [message.content for message in app._selected_conversation.messages] == [
                "before resume",
                "after resume",
            ]
            assert app._selected_conversation.msg_count_from_history == 2

    asyncio.run(exercise_app())
