"""Command-line interface for copilotexport."""

from __future__ import annotations

import argparse
from pathlib import Path

from copilotexport.exporter import default_workspace_storage, export


def main() -> int:
    """Entry point for the ``copilot-export`` command."""
    parser = argparse.ArgumentParser(
        prog="copilotexport",
        description=(
            "Export all VS Code GitHub Copilot Chat conversations to JSON and "
            "Markdown. Reads session files from VS Code's workspaceStorage "
            "directory (works on Linux, macOS, and Windows)."
        ),
    )
    parser.add_argument(
        "--src",
        type=Path,
        default=default_workspace_storage(),
        help="VS Code workspaceStorage directory (auto-detected by default)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path.cwd() / "_copilot",
        help="Output directory (default: ./_copilot)",
    )
    parser.add_argument(
        "--no-markdown",
        action="store_true",
        help="Skip Markdown rendering (raw JSON + index only, much faster)",
    )
    parser.add_argument(
        "--no-zip",
        action="store_true",
        help="Skip creating CopilotExport.zip",
    )
    parser.add_argument(
        "--no-raw",
        action="store_true",
        help="Skip copying raw VS Code session JSON (markdown/index only)",
    )
    args = parser.parse_args()

    export(
        src=args.src,
        out=args.out,
        write_markdown=not args.no_markdown,
        make_zip=not args.no_zip,
        copy_raw=not args.no_raw,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
