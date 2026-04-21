"""Core export logic for copilotexport."""

from __future__ import annotations

import datetime as _dt
import json
import platform
import re
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

# ---------------------------------------------------------------------------
# Locating the workspaceStorage directory
# ---------------------------------------------------------------------------


def default_workspace_storage() -> Path:
    """Return the default VS Code workspaceStorage path for the current OS."""
    home = Path.home()
    sysname = platform.system()
    if sysname == "Darwin":
        return home / "Library/Application Support/Code/User/workspaceStorage"
    if sysname == "Windows":
        import os

        appdata = os.environ.get("APPDATA", str(home / "AppData/Roaming"))
        return Path(appdata) / "Code/User/workspaceStorage"
    return home / ".config/Code/User/workspaceStorage"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def slugify(value: str, max_len: int = 80) -> str:
    """Convert an arbitrary string to a filesystem-safe slug."""
    value = (value or "").strip()
    value = _SAFE.sub("_", value).strip("_")
    if not value:
        value = "untitled"
    return value[:max_len]


def workspace_label(ws_dir: Path) -> str:
    """Return a friendly label for a workspace storage folder.

    Reads workspace.json (when present) to recover the original folder/workspace
    URI; falls back to the hash directory name.
    """
    info_file = ws_dir / "workspace.json"
    if info_file.exists():
        try:
            info = json.loads(info_file.read_text())
        except Exception:
            info = {}
        uri = info.get("folder") or info.get("workspace") or info.get("configuration")
        if uri:
            try:
                parsed = urlparse(uri)
                path = unquote(parsed.path)
                tail = Path(path).name or Path(path).parent.name
                if tail:
                    return f"{slugify(tail, 60)}__{ws_dir.name[:8]}"
            except Exception:
                pass
    return ws_dir.name


def ms_to_iso(ms: Any) -> str | None:
    """Convert a JavaScript millisecond timestamp to an ISO 8601 string."""
    if not isinstance(ms, (int, float)):
        return None
    try:
        return (
            _dt.datetime.fromtimestamp(ms / 1000.0, tz=_dt.timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
    except (OSError, OverflowError, ValueError):
        return None


def ms_to_date(ms: Any) -> str:
    """Return just the YYYY-MM-DD portion of a JavaScript millisecond timestamp."""
    iso = ms_to_iso(ms)
    return iso.split("T", 1)[0] if iso else "unknown-date"


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def _flat_text(node: Any) -> str:
    """Best-effort string extraction from a VS Code MarkdownString-like value."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        if "value" in node and isinstance(node["value"], str):
            return node["value"]
        if "text" in node and isinstance(node["text"], str):
            return node["text"]
    if isinstance(node, list):
        return "".join(_flat_text(x) for x in node)
    return ""


def _request_text(message: Any) -> str:
    if isinstance(message, dict):
        if isinstance(message.get("text"), str):
            return message["text"]
        parts = message.get("parts")
        if isinstance(parts, list):
            return "".join(_flat_text(p) for p in parts)
    return _flat_text(message)


def _uri_path(uri: Any) -> str | None:
    if isinstance(uri, dict):
        return uri.get("fsPath") or uri.get("path") or uri.get("external")
    if isinstance(uri, str):
        return uri
    return None


def _render_tool_call(item: dict) -> str:
    tool_id = item.get("toolId") or item.get("toolName") or "tool"
    invocation = _flat_text(item.get("invocationMessage"))
    past = _flat_text(item.get("pastTenseMessage"))
    header = f"**Tool call** `{tool_id}`"
    lines = [header]
    if invocation:
        lines.append(f"- request: {invocation}")
    if past:
        lines.append(f"- result: {past}")
    details = item.get("resultDetails")
    if isinstance(details, list) and details:
        files: list[str] = []
        for d in details:
            if isinstance(d, dict):
                p = _uri_path(d.get("uri"))
                if p and p not in files:
                    files.append(p)
        if files:
            lines.append("- files:")
            for f in files[:25]:
                lines.append(f"  - `{f}`")
            if len(files) > 25:
                lines.append(f"  - ... ({len(files) - 25} more)")
    src = item.get("source")
    if isinstance(src, dict):
        label = src.get("label") or src.get("type")
        if label:
            lines.append(f"- source: {label}")
    return "\n".join(lines)


def _render_response_items(items: Any) -> str:
    if not isinstance(items, list):
        return _flat_text(items)
    out: list[str] = []
    buf: list[str] = []

    def flush_buf() -> None:
        if buf:
            text = "".join(buf).strip()
            if text:
                out.append(text)
            buf.clear()

    for item in items:
        if isinstance(item, dict):
            kind = item.get("kind")
            if kind == "toolInvocationSerialized":
                flush_buf()
                out.append(_render_tool_call(item))
                continue
            if kind == "prepareToolInvocation":
                # Skipped: redundant with the matching toolInvocationSerialized
                continue
            if kind == "inlineReference":
                ref = item.get("inlineReference")
                p = _uri_path(ref) if isinstance(ref, (dict, str)) else None
                if p:
                    buf.append(f"`{Path(p).name}`")
                continue
            if kind in {"undoStop", "codeblockUri"}:
                continue
            if kind == "textEditGroup":
                flush_buf()
                uri = _uri_path(item.get("uri"))
                if uri:
                    out.append(f"_Edited_ `{uri}`")
                continue
            # MarkdownString-like dicts
            text = _flat_text(item)
            if text:
                buf.append(text)
                continue
        else:
            text = _flat_text(item)
            if text:
                buf.append(text)
    flush_buf()
    return "\n\n".join(out)


def render_markdown(session: dict) -> str:
    """Render a VS Code Copilot chat session dict as a Markdown transcript."""
    title = session.get("customTitle") or "Untitled conversation"
    sid = session.get("sessionId", "")
    created = ms_to_iso(session.get("creationDate")) or "?"
    last = ms_to_iso(session.get("lastMessageDate")) or "?"
    requester = session.get("requesterUsername") or "user"
    responder = session.get("responderUsername") or "GitHub Copilot"

    lines = [
        f"# {title}",
        "",
        f"- session id: `{sid}`",
        f"- created: {created}",
        f"- last message: {last}",
        f"- requester: {requester}",
        f"- responder: {responder}",
        "",
        "---",
        "",
    ]
    for idx, req in enumerate(session.get("requests") or [], start=1):
        if not isinstance(req, dict):
            continue
        ts = ms_to_iso(req.get("timestamp"))
        model = req.get("modelId") or ""
        agent = ""
        agent_obj = req.get("agent")
        if isinstance(agent_obj, dict):
            agent = agent_obj.get("name") or agent_obj.get("id") or ""
        meta_bits = [
            b
            for b in (
                ts,
                f"model: {model}" if model else "",
                f"agent: {agent}" if agent else "",
            )
            if b
        ]
        meta = "  \n".join(meta_bits)
        lines.append(f"## Turn {idx} — {requester}")
        if meta:
            lines.append(f"_{meta}_")
        lines.append("")
        user_text = _request_text(req.get("message")).strip()
        lines.append(user_text or "_(empty message)_")
        lines.append("")
        lines.append(f"## Turn {idx} — {responder}")
        lines.append("")
        rendered = _render_response_items(req.get("response")).strip()
        lines.append(rendered or "_(no response captured)_")
        result = req.get("result")
        if isinstance(result, dict) and result.get("errorDetails"):
            lines.append("")
            lines.append(f"> error: {json.dumps(result['errorDetails'])}")
        if req.get("isCanceled"):
            lines.append("")
            lines.append("> _Request was canceled._")
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main export
# ---------------------------------------------------------------------------


def export(
    src: Path,
    out: Path,
    write_markdown: bool = True,
    make_zip: bool = True,
    copy_raw: bool = True,
) -> dict:
    """Export all Copilot chat sessions found under *src* into *out*.

    Parameters
    ----------
    src:
        VS Code ``workspaceStorage`` directory.
    out:
        Destination directory that will receive ``sessions/``, ``markdown/``,
        ``index.json``, ``workspaces.json``, and ``export_info.json``.
    write_markdown:
        When ``True`` (default) render each session as a Markdown transcript.
    make_zip:
        When ``True`` (default) bundle *out* into a ``CopilotExport.zip``
        next to it.
    copy_raw:
        When ``True`` (default) copy the raw VS Code JSON files verbatim into
        ``out/sessions/``.

    Returns
    -------
    dict
        Summary with ``exportedAt``, ``source``, ``workspaces``, ``sessions``
        and (when zip was produced) ``zip``.
    """
    if not src.exists():
        raise FileNotFoundError(f"workspaceStorage not found: {src}")

    out.mkdir(parents=True, exist_ok=True)
    sessions_root = out / "sessions"
    md_root = out / "markdown"
    if copy_raw:
        sessions_root.mkdir(exist_ok=True)
    if write_markdown:
        md_root.mkdir(exist_ok=True)

    workspaces: dict[str, dict] = {}
    index: list[dict] = []

    ws_dirs = sorted(p for p in src.iterdir() if p.is_dir())
    total = 0
    for ws in ws_dirs:
        chat_dir = ws / "chatSessions"
        if not chat_dir.is_dir():
            continue
        label = workspace_label(ws)
        info_file = ws / "workspace.json"
        ws_meta: dict = {}
        if info_file.exists():
            try:
                ws_meta = json.loads(info_file.read_text())
            except Exception:
                ws_meta = {"_error": "unreadable workspace.json"}
        workspaces[ws.name] = {"label": label, **ws_meta}

        files = sorted(chat_dir.glob("*.json"))
        if not files:
            continue
        if copy_raw:
            (sessions_root / label).mkdir(parents=True, exist_ok=True)
        if write_markdown:
            (md_root / label).mkdir(parents=True, exist_ok=True)

        for f in files:
            try:
                data = json.loads(f.read_text())
            except Exception as exc:
                print(f"  ! skip {f}: {exc}", file=sys.stderr)
                continue
            sid = data.get("sessionId") or f.stem
            title = data.get("customTitle") or "Untitled"
            requests = data.get("requests") or []
            entry: dict = {
                "sessionId": sid,
                "workspaceHash": ws.name,
                "workspaceLabel": label,
                "title": title,
                "creationDate": data.get("creationDate"),
                "lastMessageDate": data.get("lastMessageDate"),
                "creationDateIso": ms_to_iso(data.get("creationDate")),
                "lastMessageDateIso": ms_to_iso(data.get("lastMessageDate")),
                "numRequests": len(requests),
                "rawPath": f"sessions/{label}/{sid}.json" if copy_raw else None,
            }
            if copy_raw:
                shutil.copy2(f, sessions_root / label / f"{sid}.json")
            if write_markdown:
                date = ms_to_date(
                    data.get("creationDate") or data.get("lastMessageDate")
                )
                fname = f"{date}_{slugify(title, 60)}_{sid[:8]}.md"
                md_path = md_root / label / fname
                try:
                    md_path.write_text(render_markdown(data))
                    entry["markdownPath"] = f"markdown/{label}/{fname}"
                except Exception as exc:
                    print(f"  ! markdown failed for {sid}: {exc}", file=sys.stderr)
            index.append(entry)
            total += 1
        print(f"  [{label}] {len(files)} sessions")

    index.sort(key=lambda e: e.get("creationDate") or 0)
    (out / "workspaces.json").write_text(json.dumps(workspaces, indent=2))
    (out / "index.json").write_text(json.dumps(index, indent=2))

    summary = {
        "exportedAt": _dt.datetime.now(tz=_dt.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "source": str(src),
        "workspaces": len(workspaces),
        "sessions": total,
    }
    (out / "export_info.json").write_text(json.dumps(summary, indent=2))
    print(f"Wrote {total} sessions across {len(workspaces)} workspaces -> {out}")

    if make_zip:
        zip_path = out.parent / "CopilotExport.zip"
        print(f"Zipping -> {zip_path}")
        with zipfile.ZipFile(
            zip_path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
            allowZip64=True,
        ) as z:
            for p in out.rglob("*"):
                if p.is_file():
                    z.write(p, p.relative_to(out.parent))
        summary["zip"] = str(zip_path)
        print(f"Done. zip size: {zip_path.stat().st_size / (1024 * 1024):.1f} MB")
    return summary
