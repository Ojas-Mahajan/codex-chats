"""CLI entry point for the Codex Chat History TUI."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from . import __version__
from .app import CodexChatsApp

# Default Codex data directory
DEFAULT_DATA_DIR = Path.home() / ".codex"


@click.command()
@click.option(
    "--data-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=DEFAULT_DATA_DIR,
    show_default=True,
    help="Path to the Codex data directory.",
)
@click.version_option(version=__version__)
def main(data_dir: Path) -> None:
    """Browse and view your Codex conversation history in the terminal.

    Launch this TUI to see all your past Codex conversations,
    search through them, and view full chat transcripts.
    """
    # Validate the data directory
    history_file = data_dir / "history.jsonl"
    if not history_file.is_file():
        click.echo(
            f"Error: No 'history.jsonl' found at {data_dir}\n"
            f"Make sure this is a valid Codex data directory.",
            err=True,
        )
        sys.exit(1)

    app = CodexChatsApp(data_dir=data_dir)
    app.run()


if __name__ == "__main__":
    main()
