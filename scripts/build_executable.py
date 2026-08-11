#!/usr/bin/env python3
"""Build the native, single-file Codex Chats executable for this host."""

from __future__ import annotations

import argparse
import platform
import subprocess
import sys
from pathlib import Path


def artifact_platform() -> str:
    """Return the supported artifact label for the current native host."""
    system = platform.system()
    machine = platform.machine().lower()

    if system == "Darwin" and machine in {"arm64", "aarch64"}:
        return "macos-arm64"
    if system == "Darwin" and machine in {"x86_64", "amd64"}:
        return "macos-intel"
    if system == "Linux" and machine in {"x86_64", "amd64"}:
        return "linux-x86_64"
    if system == "Windows" and machine in {"x86_64", "amd64"}:
        return "windows-x86_64"

    raise SystemExit(f"Unsupported build host: {system} {machine}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a one-file native Codex Chats executable."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts"),
        help="Directory where the platform-labelled artifact folder is created.",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    label = artifact_platform()
    output_dir = args.output.resolve() / label
    work_dir = root / "build" / label
    spec_dir = root / "build" / "spec"
    output_dir.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        "codex-chats",
        "--distpath",
        str(output_dir),
        "--workpath",
        str(work_dir),
        "--specpath",
        str(spec_dir),
        "--paths",
        str(root / "src"),
        "--collect-all",
        "textual",
        str(root / "scripts" / "pyinstaller_entry.py"),
    ]
    subprocess.run(command, check=True, cwd=root)


if __name__ == "__main__":
    main()
