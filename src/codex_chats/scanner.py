"""Scan the Antigravity data directory to discover and index all conversations."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from .models import Conversation
from .parser import derive_title, parse_overview

# Regex to validate UUID format for conversation IDs
UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)

# Hardcoded title map from conversation summaries (for conversations without logs)
# This maps conversation IDs to known titles from Antigravity session metadata.
KNOWN_TITLES: dict[str, str] = {
    "2d899dd1-b117-4eb1-b891-043986f2ffb8": "Fixing Nomad Atlas Data Links",
    "d8a2676a-3086-4d36-94c6-2f1a397cb60c": "Analyzing Client Invite Link",
    "0b9d39ad-12cb-4cea-893e-e85fa1d36bb8": "Explaining Medium Automation Project",
    "ee1583b6-bc92-4401-8c78-4440ad534361": "Fixing Next.js Permission Error",
    "5572530e-cf8e-457d-a43b-138ab22aac9b": "Updating Resume Certifications List",
    "52ff8c97-cd03-4ccd-b409-af91499d6c75": "Adding Asha Iyer Persona",
    "645b9b06-3867-4e75-8422-fb93b33600e7": "Understanding Medium Automation Script",
    "9fe85cbf-7684-48eb-888a-d58db01ad2e9": "Generating New Persona Profile",
    "6e664f55-71db-48ed-b185-4bf87f3e5589": "Understanding HTML Formatting Logic",
    "0be807ed-17ba-48d6-bd08-233550b34804": "Antigravity Chat History TUI App",
}


def _get_file_mtime(path: Path) -> datetime:
    """Get the last modified time of a file as an aware datetime."""
    stat = path.stat()
    return datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)


def _find_artifacts(brain_dir: Path) -> list[str]:
    """Find artifact files (markdown) in a conversation's brain directory."""
    artifacts = []
    artifacts_dir = brain_dir / "artifacts"
    if artifacts_dir.is_dir():
        for f in artifacts_dir.iterdir():
            if f.suffix == ".md":
                artifacts.append(f.name)

    # Also check root of brain dir for markdown files
    for f in brain_dir.iterdir():
        if f.suffix == ".md" and f.name not in ("README.md",):
            artifacts.append(f.name)

    return sorted(set(artifacts))


def scan_conversations(base_dir: str | Path) -> list[Conversation]:
    """Scan the Antigravity data directory and return all discovered conversations.

    Args:
        base_dir: Path to ~/.gemini/antigravity/

    Returns:
        List of Conversation objects sorted by last_modified (newest first).
    """
    base = Path(base_dir)
    conversations_dir = base / "conversations"
    brain_dir = base / "brain"

    if not conversations_dir.is_dir():
        return []

    results: list[Conversation] = []

    # Iterate through all .pb files in conversations/
    for pb_file in conversations_dir.glob("*.pb"):
        conv_id = pb_file.stem
        if not UUID_PATTERN.match(conv_id):
            continue

        last_modified = _get_file_mtime(pb_file)
        size_bytes = pb_file.stat().st_size

        # Check for brain directory and overview.txt
        conv_brain = brain_dir / conv_id
        overview_path = conv_brain / ".system_generated" / "logs" / "overview.txt"

        messages = []
        has_logs = False
        title = KNOWN_TITLES.get(conv_id, "Untitled")

        if overview_path.is_file():
            has_logs = True
            messages = parse_overview(overview_path)
            # Derive title from messages if not in known titles
            if conv_id not in KNOWN_TITLES:
                derived = derive_title(messages)
                if derived != "Untitled":
                    title = derived

        # Find artifacts
        artifacts = _find_artifacts(conv_brain) if conv_brain.is_dir() else []

        conv = Conversation(
            id=conv_id,
            title=title,
            last_modified=last_modified,
            messages=messages,
            has_logs=has_logs,
            artifacts=artifacts,
            size_bytes=size_bytes,
        )
        results.append(conv)

    # Sort by last_modified descending (newest first)
    results.sort(key=lambda c: c.last_modified, reverse=True)
    return results
