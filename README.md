# Codex Chats

Terminal UI for browsing, searching, opening, and cleaning up local Codex CLI conversation history.

`codex-chats` reads your `~/.codex` data, shows conversations in a three-pane layout, and lets you resume a selected session with `codex resume` without leaving the terminal workflow.

## Features

- **Fast metadata search**: Filter conversations by title, session ID, model, or working directory.
- **Date and model filters**: Narrow the list to Today, Yesterday, Last 7 days, Last 30 days, or a specific model such as `gpt-5.5`.
- **Directory filtering**: Use the left sidebar to show all chats or only chats from a specific project directory.
- **Conversation list grouping**: Chats are sorted newest first and grouped into Today, Yesterday, and Older sections.
- **Yazi-inspired terminal styling**: Dark pane colors, clear divider lines, readable selected rows, and hidden scrollbars keep the UI clean while preserving keyboard and mouse scrolling.
- **Lazy transcript loading**: Startup and search only load lightweight metadata. Full rollout transcripts are parsed when a conversation is selected.
- **Transcript viewer**: Read user, assistant, reasoning, tool-call, and tool-output entries in a formatted right-hand `Transcript` pane.
- **Compact image attachments**: Pasted image tags are shown as short attachment labels instead of large raw XML/path blocks.
- **Resume in Codex**: Press `Enter` or `o` to suspend the TUI and run `codex resume <session-id>` from the saved working directory when it still exists.
- **Delete sessions**: Remove a session's rollout file and matching `history.jsonl` rows after confirmation.
- **Clipboard support**: Copy the selected session ID with `c`.
- **Keyboard-first navigation**: Move between directories, conversations, and transcripts with arrow keys or `h` / `j` / `k` / `l`.
- **Custom data directory**: Point the app at another Codex data directory with `--data-dir`.

## Requirements

- Python 3.10+
- Codex CLI installed and available as `codex`
- A Codex data directory containing `history.jsonl`, usually `~/.codex`
- Python dependencies from `pyproject.toml`, including [Textual](https://textual.textualize.io/), Rich, and Click

## Installation

Create a local virtual environment and install the app in editable mode:

```bash
cd /path/to/codex-chats
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Textual is the terminal UI framework used by `codex-chats`. It provides the app shell, panes, input widgets, keyboard bindings, scrollable containers, borders, and color styling used throughout the interface.

The repository also includes a wrapper script named `codex-chats`. To run it from anywhere, make it executable and symlink it into a directory on your `PATH`:

```bash
chmod +x codex-chats
ln -s "$(pwd)/codex-chats" ~/.local/bin/codex-chats
```

The wrapper script expects the local `.venv` directory to exist at the project root. If you install the package globally or with a tool such as `pipx`, the `.venv` folder is not required, but this repository's wrapper script will not work unless `.venv` has been created and `pip install -e .` has been run inside it.

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
- `Tab` / `Shift+Tab`: Move between the search box, date filter, model filter, and pane controls.
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

  
## Screenshot of Project
<img width="2868" height="1724" alt="codex-chats working" src="https://github.com/user-attachments/assets/dff51504-9638-40f0-8dfe-e04b2ecc9608" />

## How It Works

Codex stores a lightweight command history in `~/.codex/history.jsonl` and full session transcripts under `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`.

`codex-chats` uses `history.jsonl` as the primary index, scans rollout filenames once to connect session IDs to transcript files, and reads only session metadata such as model and working directory during startup. Search, directory filters, date filters, and model filters all run against this in-memory metadata, which keeps the conversation list responsive even when transcript files are large.

When you select a conversation, the app parses that one rollout file and renders the transcript. Parsed messages are cached on the selected conversation object for the rest of the app session.

When you delete a conversation, the app removes the rollout file, prunes empty session directories, rewrites `history.jsonl` without rows for that session, and refreshes the visible list while preserving the current directory/search context where possible.





## License

MIT License
