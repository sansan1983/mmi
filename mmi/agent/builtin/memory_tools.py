"""P0-5: Memory tools for reading/writing MMI's vector memory store.

Exposes mmi/core/memory.py functions as @tool-decorated tools.
"""

from __future__ import annotations

from mmi.agent.tools import tool


@tool(
    name="memory_store",
    description="Store a memory entry in the MMI memory system. "
    "Takes session_id (required) and body (text content).",
    schema={
        "type": "object",
        "properties": {
            "session_id": {
                "type": "string",
                "description": "Session ID to associate memory with"
            },
            "body": {
                "type": "string",
                "description": "Memory content (markdown body text)"
            },
            "summary": {
                "type": "string",
                "description": "Optional summary of the content",
                "default": ""
            },
        },
        "required": ["session_id", "body"]
    }
)
def memory_store(session_id: str, body: str, summary: str = "") -> str:
    """Store a memory entry."""
    try:
        from mmi.core.memory import store_memory
        
        rec = store_memory(session_id, body, summary=summary)
        if rec:
            return f"Stored memory: id={rec.memory_id[:8] if rec.memory_id else '?'}..."
        return "Warning: duplicate or empty content, nothing stored"
    except ImportError as e:
        return f"Error: memory module not available ({e})"
    except Exception as e:
        return f"Error storing memory: {e}"


@tool(
    name="memory_search",
    description="Search memory entries by keyword. Returns matching memory records.",
    schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search keyword or phrase"
            },
            "limit": {
                "type": "integer",
                "description": "Maximum results",
                "default": 5
            },
        },
        "required": ["query"]
    }
)
def memory_search(query: str, limit: int = 5) -> str:
    """Search memory entries."""
    try:
        from mmi.core.memory import search
        
        results = search(query, k=limit)
        if not results:
            return "No matching memory entries found."
        lines = [f"Found {len(results)} results:"]
        for r in results:
            lines.append(f"  [{r.memory_id[:8]}] {r.raw_excerpt[:100]}")
        return "\n".join(lines)
    except ImportError as e:
        return f"Error: memory module not available ({e})"
    except Exception as e:
        return f"Error searching memory: {e}"


@tool(
    name="memory_count",
    description="Get total number of stored memory entries.",
    schema={
        "type": "object",
        "properties": {},
        "required": []
    }
)
def memory_count() -> str:
    """Count memory entries."""
    try:
        from mmi.core.memory import memory_count as mc
        count = mc()
        return f"Total memory entries: {count}"
    except ImportError as e:
        return f"Error: memory module not available ({e})"
    except Exception as e:
        return f"Error counting memory: {e}"
