"""CLI entry point for the Antigravity Chat History TUI."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from .app import CodexChatsApp

# Default Antigravity data directory
DEFAULT_DATA_DIR = Path.home() / ".gemini" / "antigravity"


@click.command()
@click.option(
    "--data-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=DEFAULT_DATA_DIR,
    show_default=True,
    help="Path to the Antigravity data directory.",
)
@click.version_option(package_name="codex-chats")
def main(data_dir: Path) -> None:
    """Browse and view your Antigravity conversation history in the terminal.

    Launch this TUI to see all your past Antigravity conversations,
    search through them, and view full chat transcripts.
    """
    # Validate the data directory
    conversations_dir = data_dir / "conversations"
    if not conversations_dir.is_dir():
        click.echo(
            f"Error: No 'conversations' directory found at {data_dir}\n"
            f"Make sure this is a valid Antigravity data directory.",
            err=True,
        )
        sys.exit(1)

    app = CodexChatsApp(data_dir=data_dir)
    app.run()


if __name__ == "__main__":
    main()
