"""P2 Extended Tools: search_enhanced, adb_ui, schedule_tools, video_generate.

P2-1: search_enhanced - Multi-source search (web + local BM25)
P2-4: adb_ui - Android screen UI dump via ADB
P2-5: schedule_tools - Scheduled task management
P2-6: video_generate - Video generation via Agnes API

跨平台兼容：ADB、路径等已适配 Windows/macOS/Linux。
"""

from __future__ import annotations

import json
import os
import subprocess
import time

from mmi.agent.tools import tool


# ====== P2-1: search_enhanced (real BM25 implementation) ======


@tool(
    name="search_enhanced",
    description="Search with BM25 or web. "
    "If as_web=True, searches via internet (returns placeholder — needs external search API). "
    "If as_web=False, searches local session turns via BM25 (requires session_id). "
    "Cross-platform: pure Python, no extra dependencies beyond jieba for Chinese.",
    schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query"
            },
            "as_web": {
                "type": "boolean",
                "description": "If True, search web; if False, search local turns (default: False)"
            },
            "limit": {
                "type": "integer",
                "description": "Max results (default: 5)"
            },
            "session_id": {
                "type": "string",
                "description": "Required when as_web=False: the session to search within. "
                "If not provided, searches ALL sessions."
            },
            "language": {
                "type": "string",
                "description": "Search language: 'zh-CN' or 'en-US' (default: auto-detect from query)"
            },
        },
        "required": ["query"]
    }
)
def search_enhanced(
    query: str,
    as_web: bool = False,
    limit: int = 5,
    session_id: str | None = None,
    language: str | None = None,
) -> str:
    """Search using BM25 (local) or web (placeholder).

    Local search mode (as_web=False):
      - Searches session turn content using BM25 scoring
      - If session_id is given, searches only that session
      - If session_id is None, searches ALL sessions (reads all session files)
      - Returns ranked matches with excerpts and scores

    Web search mode (as_web=True):
      - Returns placeholder — external search API needs to be configured
    """
    if not query or not query.strip():
        return "Error: empty query"

    if as_web:
        # Web search needs external API (e.g., Bing, Google, Brave)
        api_key = os.environ.get("SEARCH_API_KEY", "")
        api_provider = os.environ.get("SEARCH_PROVIDER", "")
        if api_key and api_provider:
            return (
                f"[web search] Provider: {api_provider}, "
                f"Query: {query} — search API configured, ready to use."
            )
        return (
            "[web search] No external search API configured. "
            "Set SEARCH_API_KEY and SEARCH_PROVIDER environment variables. "
            "Supported providers: bing, google, brave, duckduckgo."
        )

    # ===== Local BM25 search =====
    try:
        from mmi.core.search import score_turns, _detect_language

        if language is None:
            language = _detect_language(query)

        if session_id:
            # Search a specific session
            from mmi.core import storage
            try:
                body = storage.read_session(session_id).body
            except Exception as e:
                return f"Session '{session_id}' not found: {e}"

            # Parse turns from body
            turns = storage.parse_turns(body)
            if not turns:
                return f"No turns found in session '{session_id}'."

            # Search within this session
            scored = score_turns(turns, query, language=language)
            if not scored:
                return f"No matches found in session '{session_id}'."

            # Format results
            top = scored[:limit]
            lines = [f"📂 Session: {session_id} ({len(turns)} turns, {len(top)} matches)"]
            for idx, score in top:
                turn = turns[idx]
                role = turn.get("role", "?")
                content = (turn.get("content") or "")[:200]
                emoji = "👤" if role == "user" else "🤖"
                lines.append(f"  {emoji} Turn {idx + 1} [{role}] score={score:.2f}")
                lines.append(f"    {content}")
            return "\n".join(lines)

        else:
            # Search ALL sessions — read all session IDs, search each
            from mmi.core import storage
            session_ids = storage.list_session_ids()
            if not session_ids:
                return "No sessions found to search."

            all_results: list[tuple[str, int, float, str]] = []

            # Search up to 50 sessions at once (performance cap)
            for sid in session_ids[:50]:
                try:
                    body = storage.read_session(sid).body
                    turns = storage.parse_turns(body)
                    if not turns:
                        continue
                    scored = score_turns(turns, query, language=language)
                    for turn_idx, score in scored:
                        turn = turns[turn_idx]
                        role = turn.get("role", "?")
                        content = (turn.get("content") or "")[:300]
                        all_results.append((sid, turn_idx, score, content))
                except Exception:
                    continue  # Skip corrupt sessions

            if not all_results:
                return f"No matches found across {len(session_ids)} sessions."

            # Sort by score and limit
            all_results.sort(key=lambda x: -x[2])
            top = all_results[:limit]

            lines = [f"🔍 Global search: '{query}' ({language}, {len(all_results)} total matches)"]
            for sid, turn_idx, score, content in top:
                emoji = "👤" if "User" in content else "🤖"
                # Truncate session ID for display
                short_sid = sid[:12]
                lines.append(f"  {emoji} [{short_sid}] Turn {turn_idx + 1} score={score:.2f}")
                lines.append(f"    {content[:200]}")

            return "\n".join(lines)

    except ImportError:
        return "Error: mmi.core.search module not available. Install jieba for Chinese tokenization: pip install jieba"
    except Exception as e:
        return f"Local search error: {type(e).__name__}: {e}"


# ====== P2-4: adb_ui (cross-platform) ======


def _find_adb():
    """Find ADB executable (cross-platform).

    Searches common paths on Windows, macOS, and Linux.
    """
    candidates = []

    if os.name == "nt":
        # Windows: common Android SDK paths
        android_sdk = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
        if android_sdk:
            candidates.extend([
                os.path.join(android_sdk, "platform-tools", "adb.exe"),
                os.path.join(android_sdk, "platform-tools", "adb"),
            ])
        # Also check PATH
        candidates.extend(["adb", "adb.exe"])
        # Common install locations
        for drive in "CDE":
            for subdir in ["Users", "Users/Public"]:
                candidates.extend([
                    f"{drive}:/Users/{os.environ.get('USERNAME', '')}/AppData/Local/Android/Sdk/platform-tools/adb.exe",
                    f"{drive}:/Android/Sdk/platform-tools/adb.exe",
                ])
    else:
        # macOS / Linux
        candidates.extend([
            "/usr/local/bin/adb",
            "/opt/homebrew/bin/adb",      # macOS Homebrew (Apple Silicon)
            "/usr/bin/adb",
            "adb",
        ])
        android_sdk = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
        if android_sdk:
            candidates.append(os.path.join(android_sdk, "platform-tools", "adb"))

    for exe in candidates:
        try:
            if os.path.isfile(exe):
                r = subprocess.run(
                    [exe, "devices"],
                    capture_output=True, text=True, timeout=5,
                )
                if "device" in r.stdout and "List of devices attached" in r.stdout:
                    return exe
        except (FileNotFoundError, subprocess.TimeoutExpired, PermissionError):
            continue

    return None


@tool(
    name="adb_dump_ui",
    description="Dump Android screen UI hierarchy via ADB. Returns parsed clickable nodes. "
    "Cross-platform: auto-detects ADB on Windows/macOS/Linux.",
    schema={
        "type": "object",
        "properties": {
            "clickable_only": {
                "type": "boolean",
                "description": "Only show clickable nodes (default: True)"
            },
            "raw": {
                "type": "boolean",
                "description": "Return raw XML instead of parsed summary (default: False)"
            },
            "max_nodes": {
                "type": "integer",
                "description": "Maximum nodes to return (default: 100)"
            }
        },
        "required": []
    }
)
def adb_dump_ui(
    clickable_only: bool = True,
    raw: bool = False,
    max_nodes: int = 100,
) -> str:
    """Dump Android UI via ADB uiautomator. Cross-platform."""
    try:
        adb = _find_adb()
        if not adb:
            hints = []
            if os.name == "nt":
                hints.append("Download platform-tools from https://developer.android.com/tools/releases/platform-tools")
                hints.append("Add platform-tools to your PATH or set ANDROID_HOME")
            else:
                hints.append("macOS: brew install android-platform-tools")
                hints.append("Linux: sudo apt install adb")
            return (
                "Error: ADB not available. " +
                " ".join(hints)
            )

        r = subprocess.run(
            [adb, "shell", "uiautomator", "dump", "/sdcard/ui.xml"],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode != 0:
            return "uiautomator dump failed: " + (r.stderr or r.stdout or "unknown error")

        r2 = subprocess.run(
            [adb, "shell", "cat", "/sdcard/ui.xml"],
            capture_output=True, text=True, timeout=10,
        )
        xml = r2.stdout

        if raw:
            return xml[:5000]

        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml.encode())
        nodes = root.findall(".//node")

        results = []
        for n in nodes:
            clk = n.get("clickable", "false")
            if clickable_only and clk != "true":
                continue
            text = (n.get("text") or "").strip()
            cid = n.get("resource-id", "").split("/")[-1] if n.get("resource-id") else ""
            cls = n.get("class", "").split(".")[-1] if n.get("class") else ""
            bounds = n.get("bounds", "")
            label = text or "<" + (cid or cls) + ">"
            results.append("  [" + str(len(results)) + "] " + label + "  " + bounds)
            if len(results) >= max_nodes:
                break

        return "UI nodes (" + str(len(results)) + " of " + str(len(nodes)) + " total):\n" + "\n".join(results)

    except Exception as e:
        return "adb_dump_ui error: " + type(e).__name__ + ": " + str(e)


# ====== P2-5: schedule_tools ======

_SCHEDULE_DIR = os.path.expanduser("~/GenericAgent/sche_tasks")
_DONE_DIR = os.path.join(_SCHEDULE_DIR, "done")


def _ensure_dirs():
    os.makedirs(_SCHEDULE_DIR, exist_ok=True)
    os.makedirs(_DONE_DIR, exist_ok=True)


@tool(
    name="schedule_list",
    description="List all scheduled tasks with their status.",
    schema={"type": "object", "properties": {}, "required": []}
)
def schedule_list() -> str:
    """List all scheduled tasks."""
    _ensure_dirs()
    tasks = []
    for f in sorted(os.listdir(_SCHEDULE_DIR)):
        if not f.endswith(".json"):
            continue
        fp = os.path.join(_SCHEDULE_DIR, f)
        try:
            with open(fp) as fh:
                data = json.load(fh)
            enabled_text = "✅" if data.get("enabled", True) else "❌"
            tasks.append(
                f"  [{enabled_text}] {f[:-5]}: schedule={data.get('schedule','?')} "
                f"repeat={data.get('repeat','?')} prompt={data.get('prompt','?')[:50]}"
            )
        except Exception as e:
            tasks.append(f"  [❌] {f[:-5]}: ERROR: {e}")
    if not tasks:
        return "No scheduled tasks found."
    return "Scheduled tasks:\n" + "\n".join(tasks)


@tool(
    name="schedule_create",
    description="Create a new scheduled task.",
    schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Task name (use lowercase, no spaces)"},
            "schedule": {"type": "string", "description": "Time like 08:00 or interval like every_6h"},
            "prompt": {"type": "string", "description": "Task prompt"},
            "repeat": {
                "type": "string",
                "description": "daily|weekday|weekly|monthly|once|every_Nh|every_Nd",
                "default": "daily"
            },
        },
        "required": ["name", "schedule", "prompt"]
    }
)
def schedule_create(
    name: str,
    schedule: str,
    prompt: str,
    repeat: str = "daily",
) -> str:
    """Create a scheduled task JSON file."""
    _ensure_dirs()

    # Validate name (no slashes, no null bytes)
    if not name or any(c in name for c in "/\\:*?\"<>|\x00"):
        return f"Error: invalid task name '{name}'. Use lowercase letters, digits, underscores, hyphens."

    task = {
        "schedule": schedule,
        "repeat": repeat,
        "enabled": True,
        "prompt": prompt,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    fp = os.path.join(_SCHEDULE_DIR, name + ".json")
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(task, f, ensure_ascii=False, indent=2)
    return "Task '" + name + "' created at " + fp


@tool(
    name="schedule_update",
    description="Update an existing scheduled task (enable/disable/change fields).",
    schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Task name (without .json)"},
            "enabled": {"type": "boolean", "description": "Enable or disable the task"},
            "schedule": {"type": "string", "description": "New schedule"},
            "prompt": {"type": "string", "description": "New prompt"},
        },
        "required": ["name"]
    }
)
def schedule_update(
    name: str,
    enabled: bool | None = None,
    schedule: str | None = None,
    prompt: str | None = None,
) -> str:
    """Update a scheduled task."""
    _ensure_dirs()
    fp = os.path.join(_SCHEDULE_DIR, name + ".json")
    if not os.path.exists(fp):
        return f"Task '{name}' not found."

    with open(fp, "r", encoding="utf-8") as f:
        data = json.load(f)

    if enabled is not None:
        data["enabled"] = enabled
    if schedule is not None:
        data["schedule"] = schedule
    if prompt is not None:
        data["prompt"] = prompt
    data["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

    with open(fp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    status = "enabled" if data.get("enabled") else "disabled"
    return f"Task '{name}' updated ({status})"


@tool(
    name="schedule_delete",
    description="Delete a scheduled task.",
    schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Task name (without .json)"}
        },
        "required": ["name"]
    }
)
def schedule_delete(name: str) -> str:
    """Delete a scheduled task."""
    _ensure_dirs()
    fp = os.path.join(_SCHEDULE_DIR, name + ".json")
    if os.path.exists(fp):
        os.remove(fp)
        return "Task '" + name + "' deleted."
    return "Task '" + name + "' not found."


# ====== P2-6: video_generate ======

@tool(
    name="video_generate",
    description="Generate a video using Agnes Video API.",
    schema={
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "Video description"},
            "output_dir": {"type": "string", "description": "Output directory", "default": "./temp"},
        },
        "required": ["prompt"]
    }
)
def video_generate(prompt: str, output_dir: str = "./temp") -> str:
    """Generate video via Agnes API."""
    api_key = os.environ.get("AGNES_API_KEY") or os.environ.get("MMI_AGNES_KEY")
    api_url = os.environ.get("AGNES_API_URL", "https://api.agnesai.com/v1/video/generate")

    if not api_key:
        return (
            "Error: Agnes API key not configured. "
            "Set AGNES_API_KEY or MMI_AGNES_KEY environment variable."
        )

    try:
        import requests
        resp = requests.post(
            api_url,
            headers={
                "Authorization": "Bearer " + api_key,
                "Content-Type": "application/json",
            },
            json={"prompt": prompt, "model": "agnes-video-v2.0"},
            timeout=60,
        )
        data = resp.json()
        return json.dumps(data, ensure_ascii=False)
    except requests.exceptions.Timeout:
        return "Video generation: request timed out after 60s"
    except requests.exceptions.ConnectionError:
        return "Video generation: connection failed. Check network and API URL."
    except Exception as e:
        return "Video generation error: " + type(e).__name__ + ": " + str(e)
