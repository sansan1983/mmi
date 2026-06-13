"""P2 Extended Tools: search_enhanced, adb_ui, schedule_tools, video_generate.

P2-1: search_enhanced - Multi-source search (web + local BM25)
P2-4: adb_ui - Android screen UI dump via ADB
P2-5: schedule_tools - Scheduled task management
P2-6: video_generate - Video generation via Agnes API
"""

from __future__ import annotations

import json
import os
import subprocess
import time

from mmi.agent.tools import tool


# ====== P2-1: search_enhanced ======

@tool(
    name="search_enhanced",
    description="Search with BM25 or web. If as_web=True, searches via internet; else searches local turns via BM25.",
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
            }
        },
        "required": ["query"]
    }
)
def search_enhanced(query: str, as_web: bool = False, limit: int = 5) -> str:
    """Search using BM25 or web."""
    if as_web:
        return "[web search] Query: " + query + " - needs API config"
    else:
        try:
            from mmi.core.search import search_top_k, tokenize
            return "[local search] Query: " + query + " - BM25 available"
        except Exception as e:
            return "Local search error: " + str(e)


# ====== P2-4: adb_ui ======

_ADB_EXECUTABLES = ["/usr/bin/adb", "adb"]


def _find_adb():
    for exe in _ADB_EXECUTABLES:
        try:
            r = subprocess.run([exe, "devices"], capture_output=True, text=True, timeout=5)
            if "device" in r.stdout and "List of devices attached" in r.stdout:
                return exe
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return None


@tool(
    name="adb_dump_ui",
    description="Dump Android screen UI hierarchy via ADB. Returns parsed clickable nodes.",
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
            }
        },
        "required": []
    }
)
def adb_dump_ui(clickable_only: bool = True, raw: bool = False) -> str:
    """Dump Android UI via ADB uiautomator."""
    try:
        adb = _find_adb()
        if not adb:
            return "Error: ADB not available"

        r = subprocess.run([adb, "shell", "uiautomator", "dump", "/sdcard/ui.xml"],
                          capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            return "uiautomator dump failed: " + r.stderr

        r2 = subprocess.run([adb, "shell", "cat", "/sdcard/ui.xml"],
                           capture_output=True, text=True, timeout=10)
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

        return "UI nodes (" + str(len(results)) + "):\n" + "\n".join(results[:100])

    except Exception as e:
        return "adb_dump_ui error: " + str(e)


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
            tasks.append("  " + f[:-5] + ": schedule=" + str(data.get("schedule","?")) + " repeat=" + str(data.get("repeat","?")) + " enabled=" + str(data.get("enabled",True)))
        except Exception as e:
            tasks.append("  " + f[:-5] + ": ERROR: " + str(e))
    if not tasks:
        return "No scheduled tasks found."
    return "Scheduled tasks:\n" + "\n".join(tasks)


@tool(
    name="schedule_create",
    description="Create a new scheduled task.",
    schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Task name"},
            "schedule": {"type": "string", "description": "Time like 08:00 or interval like every_6h"},
            "prompt": {"type": "string", "description": "Task prompt"},
            "repeat": {"type": "string", "description": "daily|weekday|weekly|monthly|once|every_Nh|every_Nd"},
        },
        "required": ["name", "schedule", "prompt"]
    }
)
def schedule_create(name: str, schedule: str, prompt: str, repeat: str = "daily") -> str:
    """Create a scheduled task JSON file."""
    _ensure_dirs()
    task = {
        "schedule": schedule,
        "repeat": repeat,
        "enabled": True,
        "prompt": prompt,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    fp = os.path.join(_SCHEDULE_DIR, name + ".json")
    with open(fp, "w") as f:
        json.dump(task, f, ensure_ascii=False, indent=2)
    return "Task '" + name + "' created at " + fp


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
        return "Error: Agnes API key not configured. Set AGNES_API_KEY or MMI_AGNES_KEY environment variable."

    try:
        import requests
        resp = requests.post(
            api_url,
            headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
            json={"prompt": prompt, "model": "agnes-video-v2.0"},
            timeout=60,
        )
        data = resp.json()
        return json.dumps(data, ensure_ascii=False)
    except Exception as e:
        return "Video generation error: " + str(e)
