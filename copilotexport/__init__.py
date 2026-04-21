"""copilotexport — Export VS Code GitHub Copilot Chat conversations."""

from __future__ import annotations

import os
from pathlib import Path

with open(os.path.join(os.path.dirname(__file__), "version"), encoding="utf-8") as _f:
    __version__ = _f.read().strip()

from copilotexport.exporter import (  # noqa: E402
    default_workspace_storage,
    export,
    ms_to_date,
    ms_to_iso,
    render_markdown,
    slugify,
    workspace_label,
)

__all__ = [
    "__version__",
    "default_workspace_storage",
    "export",
    "ms_to_date",
    "ms_to_iso",
    "render_markdown",
    "slugify",
    "workspace_label",
]
