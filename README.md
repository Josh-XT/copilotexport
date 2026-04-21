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
copilotexport

# Custom source and output
copilotexport --src /path/to/Code/User/workspaceStorage --out ~/my-export

# Skip Markdown rendering (index + raw JSON only, much faster)
copilotexport --no-markdown

# Skip the zip file
copilotexport --no-zip

# Skip copying raw VS Code JSON (markdown + index only)
copilotexport --no-raw

# Bundle every session into a single zip ready to upload to AGiXT's
# /v1/conversation/import endpoint (auto-detected as the 'copilot' source).
copilotexport --agixt-zip ~/CopilotForAGiXT.zip
```

### Importing into AGiXT

`--agixt-zip PATH` writes a zip containing a single `conversations.json` —
a JSON array of raw VS Code session dicts. Upload it through the **Import
Conversations** control on the AGiXT settings page, or POST it directly:

```bash
curl -F file=@CopilotForAGiXT.zip -F agent_name=XT \
     -H "Authorization: $JWT" \
     http://localhost:7437/v1/conversation/import
```

AGiXT detects the format as `copilot`, prefixes imported conversations with
`[Copilot]`, and renders Copilot tool invocations as `[SUBACTIVITY]` blocks
in the chat UI.

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