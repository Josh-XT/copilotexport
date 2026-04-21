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


# ---------------------------------------------------------------------------
# AGiXT importer-compatible bundle
# ---------------------------------------------------------------------------


def collect_sessions(src: Path) -> list[dict]:
    """Return the raw VS Code chat-session dicts found under *src*.

    Each session also gets a few convenience keys (``workspaceHash``,
    ``workspaceLabel``) so downstream importers can attribute them, but the
    original VS Code keys (``sessionId``, ``customTitle``, ``requests``, ...)
    are preserved verbatim — this is what the AGiXT ``copilot`` parser walks.
    """
    if not src.exists():
        raise FileNotFoundError(f"workspaceStorage not found: {src}")

    sessions: list[dict] = []
    for ws in sorted(p for p in src.iterdir() if p.is_dir()):
        chat_dir = ws / "chatSessions"
        if not chat_dir.is_dir():
            continue
        label = workspace_label(ws)
        for f in sorted(chat_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text())
            except Exception as exc:
                print(f"  ! skip {f}: {exc}", file=sys.stderr)
                continue
            if not isinstance(data, dict):
                continue
            data.setdefault("workspaceHash", ws.name)
            data.setdefault("workspaceLabel", label)
            sessions.append(data)
    sessions.sort(key=lambda d: d.get("creationDate") or 0)
    return sessions


def export_agixt_zip(src: Path, zip_path: Path) -> dict:
    """Bundle all sessions found under *src* as an AGiXT-importable zip.

    The resulting archive contains a single ``conversations.json`` at the
    root — a JSON array of raw VS Code session dicts. The AGiXT
    ``/v1/conversation/import`` endpoint will auto-detect this as the
    ``copilot`` format.

    Sessions are streamed straight from disk into the zip entry one at a
    time so peak memory stays small even when the full export is many GB.

    Returns a summary dict with ``sessions``, ``zip``, and ``bytes`` fields.
    """
    if not src.exists():
        raise FileNotFoundError(f"workspaceStorage not found: {src}")

    zip_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    skipped = 0

    with zipfile.ZipFile(
        zip_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
        allowZip64=True,
    ) as z:
        info = zipfile.ZipInfo("conversations.json")
        info.compress_type = zipfile.ZIP_DEFLATED
        with z.open(info, "w", force_zip64=True) as out:
            out.write(b"[")
            first = True
            for ws in sorted(p for p in src.iterdir() if p.is_dir()):
                chat_dir = ws / "chatSessions"
                if not chat_dir.is_dir():
                    continue
                label = workspace_label(ws)
                for f in sorted(chat_dir.glob("*.json")):
                    try:
                        raw = f.read_bytes()
                        # Cheap validation + canonicalization without keeping
                        # the dict around longer than necessary.
                        data = json.loads(raw)
                    except Exception as exc:
                        print(f"  ! skip {f}: {exc}", file=sys.stderr)
                        skipped += 1
                        continue
                    if not isinstance(data, dict):
                        skipped += 1
                        continue
                    data.setdefault("workspaceHash", ws.name)
                    data.setdefault("workspaceLabel", label)
                    chunk = json.dumps(data, separators=(",", ":")).encode("utf-8")
                    del data
                    if not first:
                        out.write(b",")
                    out.write(chunk)
                    first = False
                    count += 1
                    if count % 50 == 0:
                        print(f"  ... wrote {count} sessions", flush=True)
            out.write(b"]")

    size = zip_path.stat().st_size
    print(
        f"Wrote {count} sessions"
        + (f" (skipped {skipped})" if skipped else "")
        + f" -> {zip_path} ({size / (1024 * 1024):.1f} MB)"
    )
    return {"sessions": count, "skipped": skipped, "zip": str(zip_path), "bytes": size}


def _iter_session_chunks(src: Path):
    """Yield ``(chunk_bytes, source_path)`` for every session under *src*.

    ``chunk_bytes`` is the canonical compact JSON representation of a single
    VS Code chat-session dict (with ``workspaceHash``/``workspaceLabel``
    injected) — exactly what should appear as one element of the
    ``conversations.json`` array.
    """
    for ws in sorted(p for p in src.iterdir() if p.is_dir()):
        chat_dir = ws / "chatSessions"
        if not chat_dir.is_dir():
            continue
        label = workspace_label(ws)
        for f in sorted(chat_dir.glob("*.json")):
            try:
                data = json.loads(f.read_bytes())
            except Exception as exc:
                print(f"  ! skip {f}: {exc}", file=sys.stderr)
                continue
            if not isinstance(data, dict):
                continue
            data.setdefault("workspaceHash", ws.name)
            data.setdefault("workspaceLabel", label)
            yield json.dumps(data, separators=(",", ":")).encode("utf-8"), f


def export_agixt_batches(
    src: Path,
    out_dir: Path,
    batch_mb: int = 100,
    prefix: str = "CopilotForAGiXT",
) -> dict:
    """Bundle sessions into multiple AGiXT-importable zips.

    Each output zip contains a ``conversations.json`` whose uncompressed
    payload is capped at roughly ``batch_mb`` megabytes. This keeps each
    upload well under Cloudflare's per-request limits and bounds the peak
    RAM the AGiXT server uses when it ``json.loads()`` the assembled file.

    A single oversized session always lands in its own zip so we never
    silently drop anything.
    """
    if not src.exists():
        raise FileNotFoundError(f"workspaceStorage not found: {src}")

    out_dir.mkdir(parents=True, exist_ok=True)
    cap = max(1, batch_mb) * 1024 * 1024

    batches: list[dict] = []
    batch_idx = 0
    current_zip = None
    current_out = None
    current_bytes = 0
    current_count = 0
    current_first = True
    current_path: Path | None = None
    total_count = 0

    def _open_batch() -> None:
        nonlocal current_zip, current_out, current_bytes, current_count, current_first, current_path, batch_idx
        batch_idx += 1
        current_path = out_dir / f"{prefix}_{batch_idx:03d}.zip"
        current_zip = zipfile.ZipFile(
            current_path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
            allowZip64=True,
        )
        info = zipfile.ZipInfo("conversations.json")
        info.compress_type = zipfile.ZIP_DEFLATED
        current_out = current_zip.open(info, "w", force_zip64=True)
        current_out.write(b"[")
        current_bytes = 1
        current_count = 0
        current_first = True

    def _close_batch() -> None:
        nonlocal current_zip, current_out, current_path
        if current_out is None or current_zip is None or current_path is None:
            return
        current_out.write(b"]")
        current_out.close()
        current_zip.close()
        size = current_path.stat().st_size
        batches.append(
            {
                "path": str(current_path),
                "sessions": current_count,
                "bytes": size,
            }
        )
        print(
            f"  -> {current_path.name}: {current_count} sessions, "
            f"{size / (1024 * 1024):.1f} MB compressed"
        )
        current_out = None
        current_zip = None
        current_path = None

    try:
        _open_batch()
        for chunk, _src_file in _iter_session_chunks(src):
            sep = b"" if current_first else b","
            projected = current_bytes + len(sep) + len(chunk) + 1  # +1 for "]"
            if projected > cap and current_count > 0:
                _close_batch()
                _open_batch()
                sep = b""
            assert current_out is not None
            current_out.write(sep)
            current_out.write(chunk)
            current_bytes += len(sep) + len(chunk)
            current_count += 1
            current_first = False
            total_count += 1
            if total_count % 50 == 0:
                print(f"  ... processed {total_count} sessions", flush=True)
        if current_count > 0:
            _close_batch()
        else:
            # Empty trailing batch (no sessions hit it). Discard it.
            assert (
                current_out is not None
                and current_zip is not None
                and current_path is not None
            )
            current_out.write(b"]")
            current_out.close()
            current_zip.close()
            current_path.unlink(missing_ok=True)
    except BaseException:
        if current_out is not None:
            try:
                current_out.close()
            except Exception:
                pass
        if current_zip is not None:
            try:
                current_zip.close()
            except Exception:
                pass
        raise

    print(
        f"Wrote {total_count} sessions across {len(batches)} batch zip(s) "
        f"(cap ~{batch_mb} MB uncompressed each) -> {out_dir}"
    )
    return {"sessions": total_count, "batches": batches, "out_dir": str(out_dir)}
