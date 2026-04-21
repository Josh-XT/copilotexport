# copilotexport

Export all of your VS Code GitHub Copilot Chat conversations — including full tool-call history — to JSON and Markdown. Mirrors the layout of ChatGPT and Claude exports.

## Installation

```bash
pip install copilotexport
```

## Usage

### CLI

```bash
# Default: bundle every Copilot session into ./CopilotForAGiXT.zip,
# ready to upload to AGiXT (Conversations sidebar -> Import).
copilotexport

# Write the zip somewhere else
copilotexport --out ~/CopilotForAGiXT.zip

# Custom source workspaceStorage directory
copilotexport --src /path/to/Code/User/workspaceStorage

# Full human-browseable export tree (raw JSON + Markdown + index +
# CopilotExport.zip) — slower, useful for grepping / archiving.
copilotexport --full
copilotexport --full --out ~/my-export
copilotexport --full --no-markdown   # skip Markdown rendering (much faster)
copilotexport --full --no-zip        # skip CopilotExport.zip
copilotexport --full --no-raw        # skip raw VS Code JSON copies
```

### Importing into AGiXT

The default mode writes a zip containing a single `conversations.json` —
a JSON array of raw VS Code session dicts. Upload it through the **Import
Conversations** control in the AGiXT web UI, or POST it directly:

```bash
curl -F file=@CopilotForAGiXT.zip -F agent_name=XT \
     -H "Authorization: $JWT" \
     http://localhost:7437/v1/conversation/import
```

AGiXT detects the format as `copilot`, prefixes imported conversations with
`[Copilot]`, preserves each conversation's original timestamps, and renders
Copilot tool invocations / thinking blocks as `[SUBACTIVITY]` entries in the
chat UI.

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
