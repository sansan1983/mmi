"""P3-P4 Tool Wrappers — 6 existing modules exposed as @tool.

P3-1: skill_tools (list, search, create, delete)  
P3-2: trace_tools (query, stats, turn_count)
P3-3: provider_health (health_check, list_states)
P3-6: key_tools (store_api_key, resolve_key, key_source)
P4-1: mcp_tools (list_tools, call_tool)
P4-2: audit_tools (audit_text)
"""

from __future__ import annotations

import json

from mmi.agent.tools import tool

# ---------------------------------------------------------------------------
# P3-1: Skill tools
# ---------------------------------------------------------------------------


@tool(
    name="skill_list",
    description="List all registered skills in the skill library.",
    schema={"type": "object", "properties": {}, "required": []},
)
def skill_list() -> str:
    """List all skills."""
    try:
        from mmi.agent.skill import SkillLibrary

        lib = SkillLibrary.get_instance()
        skills = lib._load_all()
        if not skills:
            return "No skills found."
        lines = []
        for sid, skill in sorted(skills.items()):
            lines.append(f"  {sid}: {skill.name}")
        return f"Skills ({len(lines)}):\n" + "\n".join(lines)
    except Exception as e:
        return f"skill_list error: {e}"


@tool(
    name="skill_search",
    description="Search skills by query (BM25-based matching).",
    schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "limit": {"type": "integer", "description": "Max results", "default": 5},
        },
        "required": ["query"],
    },
)
def skill_search(query: str, limit: int = 5) -> str:
    """Search skills matching query."""
    try:
        from mmi.agent.skill import SkillLibrary

        lib = SkillLibrary.get_instance()
        results = lib.match(query, limit=limit)
        if not results:
            return f"No skills matched: {query}"
        lines = [f"  {s.skill_id}: {s.name}" for s in results]
        return f"Matched ({len(lines)}):\n" + "\n".join(lines)
    except Exception as e:
        return f"skill_search error: {e}"


@tool(
    name="skill_create",
    description="Create a new skill with name, description, and prompt.",
    schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Skill name"},
            "prompt": {"type": "string", "description": "Skill prompt"},
        },
        "required": ["name", "prompt"],
    },
)
def skill_create(name: str, prompt: str) -> str:
    """Create a new skill."""
    try:
        from mmi.agent.skill import Skill, SkillLibrary

        lib = SkillLibrary.get_instance()
        from mmi.core.timestamp import new_session_id

        skill = Skill(
            skill_id=new_session_id(),
            name=name,
            prompt=prompt,
        )
        lib.create(skill)
        return f"Created skill: {skill.skill_id} ({name})"
    except Exception as e:
        return f"skill_create error: {e}"


@tool(
    name="skill_delete",
    description="Deprecate/delete a skill by ID.",
    schema={
        "type": "object",
        "properties": {
            "skill_id": {"type": "string", "description": "Skill ID to delete"},
        },
        "required": ["skill_id"],
    },
)
def skill_delete(skill_id: str) -> str:
    """Delete a skill."""
    try:
        from mmi.agent.skill import SkillLibrary

        lib = SkillLibrary.get_instance()
        lib.deprecate(skill_id)
        return f"Deprecated skill: {skill_id}"
    except Exception as e:
        return f"skill_delete error: {e}"


# ---------------------------------------------------------------------------
# P3-2: Trace tools
# ---------------------------------------------------------------------------


@tool(
    name="trace_query",
    description="Query traces by session_id.",
    schema={
        "type": "object",
        "properties": {
            "session_id": {"type": "string", "description": "Session ID"},
            "limit": {"type": "integer", "description": "Max results", "default": 10},
        },
        "required": ["session_id"],
    },
)
def trace_query(session_id: str, limit: int = 10) -> str:
    """Query traces for a session."""
    try:
        from mmi.agent.trace import Tracer

        t = Tracer.get_instance()
        records = t.query(session_id=session_id, limit=limit)
        if not records:
            return f"No traces for session: {session_id}"
        lines = [f"  [{r.turn_idx}] {r.role}: {str(r.content)[:80]}" for r in records]
        return f"Traces ({len(lines)}):\n" + "\n".join(lines)
    except Exception as e:
        return f"trace_query error: {e}"


@tool(
    name="trace_stats",
    description="Get trace statistics across all sessions.",
    schema={"type": "object", "properties": {}, "required": []},
)
def trace_stats() -> str:
    """Get trace stats."""
    try:
        from mmi.agent.trace import Tracer

        t = Tracer.get_instance()
        stats = t.stats()
        return json.dumps(stats, indent=2)
    except Exception as e:
        return f"trace_stats error: {e}"


# ---------------------------------------------------------------------------
# P3-3: Provider Health tools
# ---------------------------------------------------------------------------


@tool(
    name="provider_health",
    description="Get health status of all LLM providers.",
    schema={"type": "object", "properties": {}, "required": []},
)
def provider_health() -> str:
    """Get all provider health states."""
    try:
        from mmi.core.provider_health import ProviderHealthMonitor

        mon = ProviderHealthMonitor.get_instance()
        states = mon.get_all_states()
        if not states:
            return "No providers tracked."
        lines = [f"  {name}: {state.value}" for name, state in states.items()]
        return "Provider Health:\n" + "\n".join(lines)
    except Exception as e:
        return f"provider_health error: {e}"


# ---------------------------------------------------------------------------
# P3-6: Key tools
# ---------------------------------------------------------------------------


@tool(
    name="store_api_key",
    description="Store an API key securely (optionally in keyring).",
    schema={
        "type": "object",
        "properties": {
            "api_key": {"type": "string", "description": "API key to store"},
            "use_keyring": {
                "type": "boolean",
                "description": "Use system keyring",
                "default": False,
            },
        },
        "required": ["api_key"],
    },
)
def store_api_key(api_key: str, use_keyring: bool = False) -> str:
    """Store API key."""
    try:
        from mmi.core.config import store_api_key as _store

        ok = _store(api_key, use_keyring=use_keyring)
        if ok:
            return f"API key stored (keyring={use_keyring})"
        return "Failed to store API key"
    except Exception as e:
        return f"store_api_key error: {e}"


@tool(
    name="resolve_api_key",
    description="Resolve API key for a provider (supports keyring:// syntax).",
    schema={
        "type": "object",
        "properties": {
            "provider": {"type": "string", "description": "Provider name or key"},
        },
        "required": ["provider"],
    },
)
def resolve_api_key(provider: str) -> str:
    """Resolve an API key."""
    try:
        from mmi.core.config import resolve_api_key as _resolve, mask_api_key

        key = _resolve(provider)
        if not key:
            return f"No key resolved for: {provider}"
        return f"Resolved: {mask_api_key(key)}"
    except Exception as e:
        return f"resolve_api_key error: {e}"


# ---------------------------------------------------------------------------
# P4-1: MCP tools
# ---------------------------------------------------------------------------


@tool(
    name="mcp_list_tools",
    description="List all registered MCP tools.",
    schema={"type": "object", "properties": {}, "required": []},
)
def mcp_list_tools() -> str:
    """List MCP tools."""
    try:
        from mmi.core.mcp_server import MCPServer

        srv = MCPServer.get_instance()
        tools = srv.list_tools()
        if not tools:
            return "No MCP tools registered."
        lines = [f"  {t.name}: {t.description[:60]}" for t in tools]
        return f"MCP Tools ({len(lines)}):\n" + "\n".join(lines)
    except Exception as e:
        return f"mcp_list_tools error: {e}"


@tool(
    name="mcp_call",
    description="Call an MCP tool with a request.",
    schema={
        "type": "object",
        "properties": {
            "tool_name": {"type": "string", "description": "Tool name"},
            "arguments": {
                "type": "string",
                "description": "JSON string of arguments",
            },
        },
        "required": ["tool_name", "arguments"],
    },
)
def mcp_call(tool_name: str, arguments: str) -> str:
    """Call an MCP tool."""
    try:
        from mmi.core.mcp_server import MCPServer

        srv = MCPServer.get_instance()
        args = json.loads(arguments) if arguments.strip() else {}
        req = {"tool": tool_name, "arguments": args}
        resp = srv.handle_request(req)
        return json.dumps(resp.to_dict(), indent=2)
    except Exception as e:
        return f"mcp_call error: {e}"


# ---------------------------------------------------------------------------
# P4-2: Audit tools
# ---------------------------------------------------------------------------


@tool(
    name="audit_text",
    description="Run LLM Deep Audit on text (two-layer: rules + LLM).",
    schema={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Text to audit"},
        },
        "required": ["text"],
    },
)
def audit_text(text: str) -> str:
    """Run deep audit on text."""
    try:
        from mmi.core.audit import AuditEngine

        engine = AuditEngine.get_instance()
        result = engine.audit(text)
        return json.dumps(
            {
                "is_safe": result.is_safe(),
                "risk_score": result.risk_score,
                "flags": result.flags,
            },
            indent=2,
        )
    except Exception as e:
        return f"audit_text error: {e}"
