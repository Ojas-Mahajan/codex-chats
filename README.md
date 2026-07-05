<img width="2753" height="1556" alt="Screenshot from 2026-07-05 21-37-09" src="https://github.com/user-attachments/assets/bbcf3943-f32f-4abe-ab09-49829cb79a30" /># Codex Chats

Terminal UI for browsing, searching, opening, and cleaning up local Codex CLI conversation history.

`codex-chats` reads your `~/.codex` data, shows conversations in a three-pane layout, and lets you resume a selected session with `codex resume` without leaving the terminal workflow.

## Features

- **Fast metadata search**: Filter conversations by title, session ID, model, or working directory.
- **Directory filtering**: Use the left sidebar to show all chats or only chats from a specific project directory.
- **Conversation list grouping**: Chats are sorted newest first and grouped into Today, Yesterday, and Older sections.
- **Lazy transcript loading**: Startup and search only load lightweight metadata. Full rollout transcripts are parsed when a conversation is selected.
- **Transcript viewer**: Read user, assistant, reasoning, tool-call, and tool-output entries in a formatted right-hand pane.
- **Resume in Codex**: Press `Enter` or `o` to suspend the TUI and run `codex resume <session-id>` from the saved working directory when it still exists.
- **Delete sessions**: Remove a session's rollout file and matching `history.jsonl` rows after confirmation.
- **Clipboard support**: Copy the selected session ID with `c`.
- **Keyboard-first navigation**: Move between directories, conversations, and transcripts with arrow keys or `h` / `j` / `k` / `l`.
- **Custom data directory**: Point the app at another Codex data directory with `--data-dir`.

## Requirements

- Python 3.10+
- Codex CLI installed and available as `codex`
- A Codex data directory containing `history.jsonl`, usually `~/.codex`

## Installation

```bash
cd /path/to/codex-chats
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

The repository also includes a wrapper script named `codex-chats`. To run it from anywhere, make it executable and symlink it into a directory on your `PATH`:

```bash
chmod +x codex-chats
ln -s "$(pwd)/codex-chats" ~/.local/bin/codex-chats
```

## Usage

```bash
codex-chats
```

Use a different Codex data directory:

```bash
codex-chats --data-dir /path/to/.codex
```

## Keyboard Shortcuts

- `Up` / `Down` or `j` / `k`: Move through the focused directory list, conversation list, or transcript.
- `/`: Focus the search box.
- `Escape`: Return focus to the conversation list.
- `Left` or `h`: Move focus from conversations to directories, or from transcript back to conversations.
- `Right` or `l`: Move focus from directories to conversations, or from conversations to transcript.
- `Enter` on a directory: Apply that directory filter.
- `Enter` or `o` on a conversation: Resume the selected session in Codex.
- `d` or `Delete`: Delete the selected session after confirmation.
- `c` or `Escape` in the delete dialog: Cancel deletion.
- `c`: Copy the selected session ID.
- `PageUp` / `PageDown`, `Home`, `End`: Navigate the transcript viewer.
- `q`: Quit.

## How It Works

Codex stores a lightweight command history in `~/.codex/history.jsonl` and full session transcripts under `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`.

`codex-chats` uses `history.jsonl` as the primary index, scans rollout filenames once to connect session IDs to transcript files, and reads only session metadata such as model and working directory during startup. This keeps the conversation list and search responsive even when transcript files are large.

When you select a conversation, the app parses that one rollout file and renders the transcript. Parsed messages are cached on the selected conversation object for the rest of the app session.

When you delete a conversation, the app removes the rollout file, prunes empty session directories, rewrites `history.jsonl` without rows for that session, and refreshes the visible list while preserving the current directory/search context where possible.


## Screenshot of Project
<img width="2753" height="1556" alt="Screenshot from 2026-07-05 21-37-09" src="https://github.com/user-attachments/assets/2547db17-6bc4-4d48-a1f3-701f0657a979" />



## License

MIT License
