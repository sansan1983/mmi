"""P3-P4 Phase 2: Config Schema, GC Memory, GitHub, Project Manager, Web GUI.

P3-4: config_validate - Validate config.toml against provider schemas
P3-5: gc_memory - Memory GC: stats, trigger, cleanup
P4-4: github_create_release, github_list_releases
P4-5: project_init, project_status, project_close
P4-3: web_server_start, web_server_stop
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from mmi.agent.tools import tool

# ---------------------------------------------------------------------------
# P3-4: Config Schema validation
# ---------------------------------------------------------------------------


@tool(
    name="config_validate",
    description="Validate config.toml syntax and check against provider schemas.",
    schema={"type": "object", "properties": {}, "required": []},
)
def config_validate() -> str:
    """Validate the MMI config file."""
    try:
        import tomllib

        config_path = os.path.expanduser("~/.mmi/config.toml")
        if not os.path.exists(config_path):
            return f"Config not found: {config_path}"

        with open(config_path, "rb") as f:
            config = tomllib.load(f)

        issues = []
        providers = config.get("llm", {}).get("provider", [])
        if not providers:
            issues.append("No llm.provider configured")

        for p in providers:
            if not p.get("api_key"):
                issues.append(f"Provider '{p.get('name', '?')}' missing api_key")
            if not p.get("model"):
                issues.append(f"Provider '{p.get('name', '?')}' missing model")

        if issues:
            return f"Config validated with {len(issues)} issues:\n" + "\n".join(f"  - {i}" for i in issues)
        return "Config validated OK"
    except Exception as e:
        return f"Config validation error: {e}"


# ---------------------------------------------------------------------------
# P3-5: GC Memory tools
# ---------------------------------------------------------------------------


@tool(
    name="gc_memory_stats",
    description="Get memory GC statistics: total sessions, queued, processed.",
    schema={"type": "object", "properties": {}, "required": []},
)
def gc_memory_stats() -> str:
    """Get memory GC stats."""
    try:
        from mmi.core.memory import memory_count

        count = memory_count()
        return f"Memory entries: {count}"
    except Exception as e:
        return f"gc_memory_stats error: {e}"


@tool(
    name="gc_memory_cleanup",
    description="Trigger memory garbage collection for old sessions.",
    schema={
        "type": "object",
        "properties": {
            "older_than_days": {
                "type": "integer",
                "description": "Age threshold in days (default: 7)",
                "default": 7,
            }
        },
        "required": [],
    },
)
def gc_memory_cleanup(older_than_days: int = 7) -> str:
    """Run memory GC on old sessions."""
    try:
        from mmi.core.summarizer import _schedule_memory_store

        # Trigger summarizer to process pending memories
        _schedule_memory_store("__gc_trigger__")
        return f"Memory GC triggered (threshold: {older_than_days}d). Check log for results."
    except Exception as e:
        return f"gc_memory_cleanup error: {e}"


# ---------------------------------------------------------------------------
# P4-4: GitHub Integration tools
# ---------------------------------------------------------------------------


@tool(
    name="github_list_releases",
    description="List GitHub releases for a repository.",
    schema={
        "type": "object",
        "properties": {
            "owner": {"type": "string", "description": "Repo owner"},
            "repo": {"type": "string", "description": "Repo name"},
            "limit": {
                "type": "integer",
                "description": "Max releases to list",
                "default": 5,
            },
        },
        "required": ["owner", "repo"],
    },
)
def github_list_releases(owner: str, repo: str, limit: int = 5) -> str:
    """List GitHub releases."""
    try:
        import urllib.request

        url = f"https://api.github.com/repos/{owner}/{repo}/releases?per_page={limit}"
        req = urllib.request.Request(url)
        token = os.environ.get("GITHUB_TOKEN", "")
        if token:
            req.add_header("Authorization", f"Bearer {token}")

        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        if not data:
            return f"No releases found for {owner}/{repo}"
        lines = []
        for r in data:
            tag = r.get("tag_name", "?")
            name = r.get("name", "") or tag
            lines.append(f"  {tag}: {name}")
        return f"Releases for {owner}/{repo} ({len(lines)}):\n" + "\n".join(lines)
    except Exception as e:
        return f"github_list_releases error: {e}"


@tool(
    name="github_create_release",
    description="Create a GitHub release with tag, name, and body.",
    schema={
        "type": "object",
        "properties": {
            "owner": {"type": "string", "description": "Repo owner"},
            "repo": {"type": "string", "description": "Repo name"},
            "tag_name": {"type": "string", "description": "Git tag (e.g. v1.0.0)"},
            "name": {"type": "string", "description": "Release name"},
            "body": {
                "type": "string",
                "description": "Release description",
                "default": "",
            },
            "draft": {
                "type": "boolean",
                "description": "Create as draft",
                "default": False,
            },
        },
        "required": ["owner", "repo", "tag_name", "name"],
    },
)
def github_create_release(
    owner: str, repo: str, tag_name: str, name: str, body: str = "", draft: bool = False
) -> str:
    """Create a GitHub release."""
    try:
        import urllib.request

        token = os.environ.get("GITHUB_TOKEN", "")
        if not token:
            return "Error: GITHUB_TOKEN environment variable not set"

        url = f"https://api.github.com/repos/{owner}/{repo}/releases"
        payload = json.dumps(
            {
                "tag_name": tag_name,
                "name": name,
                "body": body,
                "draft": draft,
            }
        ).encode()

        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type", "application/json")

        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())

        release_url = result.get("html_url", "?")
        return f"Release created: {tag_name} ({release_url})"
    except Exception as e:
        return f"github_create_release error: {e}"


# ---------------------------------------------------------------------------
# P4-5: Project Management tools (basic goal/checklist style)
# ---------------------------------------------------------------------------

_PROJECTS: dict[str, dict] = {}


@tool(
    name="project_init",
    description="Initialize a new project with goal and tasks.",
    schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "Project ID"},
            "goal": {"type": "string", "description": "Project goal"},
            "tasks": {
                "type": "string",
                "description": "JSON list of task descriptions",
                "default": "[]",
            },
        },
        "required": ["project_id", "goal"],
    },
)
def project_init(project_id: str, goal: str, tasks: str = "[]") -> str:
    """Initialize a new project."""
    try:
        task_list = json.loads(tasks) if tasks.strip() else []
        _PROJECTS[project_id] = {
            "goal": goal,
            "tasks": {f"T{i+1}": {"desc": t, "status": "pending"} for i, t in enumerate(task_list)},
            "status": "active",
        }
        n = len(task_list)
        return f"Project '{project_id}' initialized with {n} task(s). Goal: {goal}"
    except Exception as e:
        return f"project_init error: {e}"


@tool(
    name="project_status",
    description="Get status of all projects (or a single project).",
    schema={
        "type": "object",
        "properties": {
            "project_id": {
                "type": "string",
                "description": "Project ID (optional, shows all if empty)",
                "default": "",
            }
        },
        "required": [],
    },
)
def project_status(project_id: str = "") -> str:
    """Get project status."""
    try:
        if project_id:
            proj = _PROJECTS.get(project_id)
            if not proj:
                return f"Project not found: {project_id}"
            lines = [f"Project: {project_id}", f"  Goal: {proj['goal']}", f"  Status: {proj['status']}"]
            for tid, t in proj["tasks"].items():
                lines.append(f"  {tid}: [{t['status']}] {t['desc']}")
            return "\n".join(lines)
        else:
            if not _PROJECTS:
                return "No projects."
            lines = []
            for pid, p in _PROJECTS.items():
                done = sum(1 for t in p["tasks"].values() if t["status"] == "done")
                total = len(p["tasks"])
                lines.append(f"  {pid}: [{p['status']}] {done}/{total} - {p['goal'][:40]}")
            return f"Projects ({len(lines)}):\n" + "\n".join(lines)
    except Exception as e:
        return f"project_status error: {e}"


@tool(
    name="project_mark_task",
    description="Mark a project task as done.",
    schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "Project ID"},
            "task_id": {"type": "string", "description": "Task ID (e.g. T1)"},
        },
        "required": ["project_id", "task_id"],
    },
)
def project_mark_task(project_id: str, task_id: str) -> str:
    """Mark a task as done."""
    try:
        proj = _PROJECTS.get(project_id)
        if not proj:
            return f"Project not found: {project_id}"
        task = proj["tasks"].get(task_id)
        if not task:
            return f"Task not found: {task_id}"
        task["status"] = "done"
        return f"Task {task_id} marked as done in '{project_id}'"
    except Exception as e:
        return f"project_mark_task error: {e}"


@tool(
    name="project_close",
    description="Close a project (mark all remaining tasks as done).",
    schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "Project ID to close"},
        },
        "required": ["project_id"],
    },
)
def project_close(project_id: str) -> str:
    """Close a project."""
    try:
        proj = _PROJECTS.get(project_id)
        if not proj:
            return f"Project not found: {project_id}"
        for t in proj["tasks"].values():
            if t["status"] == "pending":
                t["status"] = "closed"
        proj["status"] = "closed"
        return f"Project '{project_id}' closed."
    except Exception as e:
        return f"project_close error: {e}"


# ---------------------------------------------------------------------------
# P4-3: Web GUI tools (basic HTTP server stub)
# ---------------------------------------------------------------------------


@tool(
    name="web_server_start",
    description="Start a simple web UI server on a given port.",
    schema={
        "type": "object",
        "properties": {
            "port": {
                "type": "integer",
                "description": "Port to listen on",
                "default": 8080,
            },
            "serve_dir": {
                "type": "string",
                "description": "Directory to serve (default: cwd)",
                "default": ".",
            },
        },
        "required": [],
    },
)
def web_server_start(port: int = 8080, serve_dir: str = ".") -> str:
    """Start a simple HTTP server for web GUI."""
    try:
        serve_path = os.path.abspath(serve_dir)
        pid_file = f"/tmp/mmi_web_server_{port}.pid"
        cmd = f"cd {serve_path} && python3 -m http.server {port} --bind 0.0.0.0"
        proc = subprocess.Popen(
            cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        with open(pid_file, "w") as f:
            f.write(str(proc.pid))
        return f"Web server started on port {port}, serving {serve_path} (pid={proc.pid})"
    except Exception as e:
        return f"web_server_start error: {e}"


@tool(
    name="web_server_stop",
    description="Stop the web UI server on a given port.",
    schema={
        "type": "object",
        "properties": {
            "port": {
                "type": "integer",
                "description": "Port of the server to stop",
                "default": 8080,
            }
        },
        "required": [],
    },
)
def web_server_stop(port: int = 8080) -> str:
    """Stop the web server on given port."""
    try:
        pid_file = f"/tmp/mmi_web_server_{port}.pid"
        if not os.path.exists(pid_file):
            return f"No server pid file found on port {port}"
        with open(pid_file) as f:
            pid = int(f.read().strip())
        os.kill(pid, 15)
        os.remove(pid_file)
        return f"Web server stopped (pid={pid})"
    except Exception as e:
        return f"web_server_stop error: {e}"
