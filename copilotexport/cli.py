"""Command-line interface for copilotexport."""

from __future__ import annotations

import argparse
from pathlib import Path

from copilotexport.exporter import (
    default_workspace_storage,
    export,
    export_agixt_batches,
    export_agixt_zip,
)


def main() -> int:
    """Entry point for the ``copilotexport`` command."""
    parser = argparse.ArgumentParser(
        prog="copilotexport",
        description=(
            "Export all VS Code GitHub Copilot Chat conversations. By default "
            "writes a single AGiXT-importable zip (CopilotForAGiXT.zip) "
            "containing every session, ready to upload via the AGiXT "
            "Conversations 'Import' button. Pass --full to instead write the "
            "human-browseable export tree (raw JSON + Markdown + index)."
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
        default=None,
        help=(
            "Output path. In default (AGiXT) mode this is the zip file "
            "(default: ./CopilotForAGiXT.zip). With --full this is the "
            "directory to populate (default: ./_copilot)."
        ),
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help=(
            "Write the full human-browseable export tree (raw JSON, "
            "Markdown, index.md, and CopilotExport.zip) instead of the "
            "single AGiXT import zip."
        ),
    )
    parser.add_argument(
        "--no-markdown",
        action="store_true",
        help="(--full only) Skip Markdown rendering, much faster",
    )
    parser.add_argument(
        "--no-zip",
        action="store_true",
        help="(--full only) Skip creating CopilotExport.zip",
    )
    parser.add_argument(
        "--no-raw",
        action="store_true",
        help="(--full only) Skip copying raw VS Code session JSON",
    )
    parser.add_argument(
        "--agixt-zip",
        type=Path,
        metavar="PATH",
        help=(
            "Deprecated alias for the default mode with an explicit output "
            "path. Equivalent to: copilotexport --out PATH"
        ),
    )
    parser.add_argument(
        "--agixt-batches",
        type=Path,
        metavar="DIR",
        help=(
            "Instead of one zip, write multiple AGiXT-importable zips into "
            "DIR (CopilotForAGiXT_001.zip, _002.zip, ...). Each zip's "
            "uncompressed conversations.json is capped at --batch-mb. Use "
            "this only if your AGiXT proxy rejects very large uploads; the "
            "default single-zip mode is preferred."
        ),
    )
    parser.add_argument(
        "--batch-mb",
        type=int,
        default=100,
        metavar="MB",
        help=(
            "With --agixt-batches, max uncompressed JSON size per zip in "
            "megabytes (default: 100)."
        ),
    )
    args = parser.parse_args()

    if args.agixt_batches is not None:
        export_agixt_batches(
            src=args.src,
            out_dir=args.agixt_batches,
            batch_mb=args.batch_mb,
        )
        return 0

    if args.full:
        out_dir = args.out if args.out is not None else Path.cwd() / "_copilot"
        export(
            src=args.src,
            out=out_dir,
            write_markdown=not args.no_markdown,
            make_zip=not args.no_zip,
            copy_raw=not args.no_raw,
        )
        return 0

    # Default: single AGiXT-importable zip.
    zip_path = args.agixt_zip or args.out or (Path.cwd() / "CopilotForAGiXT.zip")
    summary = export_agixt_zip(src=args.src, zip_path=zip_path)
    print(
        f"Wrote {summary['zip']} "
        f"({summary['sessions']} sessions, "
        f"{summary['bytes'] / (1024 * 1024):.1f} MB)"
    )
    print(
        "Upload it from the AGiXT web UI: Conversations sidebar -> "
        "Import (it auto-detects Copilot exports)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
