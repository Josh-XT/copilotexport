# copilotexport

Export all of your VS Code GitHub Copilot Chat conversations — including full tool-call history — to JSON and Markdown. Mirrors the layout of ChatGPT and Claude exports.

## Installation

```bash
pip install copilotexport
```

## Usage

### CLI

```bash
# Export everything to ./_copilot/ and create CopilotExport.zip
copilot-export

# Custom source and output
copilot-export --src /path/to/Code/User/workspaceStorage --out ~/my-export

# Skip Markdown rendering (index + raw JSON only, much faster)
copilot-export --no-markdown

# Skip the zip file
copilot-export --no-zip

# Skip copying raw VS Code JSON (markdown + index only)
copilot-export --no-raw
```

### Python API

```python
from copilotexport import export, default_workspace_storage
from pathlib import Path

summary = export(
    src=default_workspace_storage(),
    out=Path("_copilot"),
    write_markdown=True,
    make_zip=True,
    copy_raw=True,
)
print(summary)
```

## Output layout

```
_copilot/
├── export_info.json                         # run summary
├── index.json                               # flat metadata for all sessions
├── workspaces.json                          # wsHash → folder URI map
├── sessions/
│   └── <workspace_label>/
│       └── <sessionId>.json                 # verbatim VS Code session file
└── markdown/
    └── <workspace_label>/
        └── <YYYY-MM-DD>_<title>_<id8>.md   # human-readable transcript
```

Each Markdown transcript includes:

- Session metadata (title, session ID, timestamps, model, agent)
- User messages
- Assistant responses with prose rendered inline
- **Tool calls** rendered as structured blocks showing the tool name, request summary, result summary, and any file paths touched

## Platform support

VS Code's `workspaceStorage` is auto-detected on Linux, macOS, and Windows.

| OS      | Default path |
|---------|-------------|
| Linux   | `~/.config/Code/User/workspaceStorage` |
| macOS   | `~/Library/Application Support/Code/User/workspaceStorage` |
| Windows | `%APPDATA%\Code\User\workspaceStorage` |

## License

MIT — Copyright (c) DevXT LLC 2026