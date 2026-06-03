"""Tool registry with @tool decorator and auto-discovery."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, ClassVar, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


@dataclass
class ToolDef:
    """Metadata describing a registered tool.

    Attributes
    ----------
    name : str
        Unique tool identifier used in tool calls.
    description : str
        Human-readable description shown to the LLM.
    schema : dict
        JSON Schema for the tool's input parameters.
    func : Callable
        The actual Python callable.
    """

    name: str
    description: str
    schema: dict = field(default_factory=dict)
    func: Callable[..., Any] = field(repr=False)


# --------------------------------------------------------------------------


class ToolRegistry:
    """Global registry of available tools.

    Provides the ``@tool`` decorator for registration and a ``call()`` method
    for execution by agents or the orchestrator.
    """

    _instance: ClassVar[ToolRegistry | None] = None

    def __init__(self) -> None:
        self._tools: dict[str, ToolDef] = {}

    @classmethod
    def get_instance(cls) -> ToolRegistry:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, tool_def: ToolDef) -> None:
        """Add a tool to the registry."""
        self._tools[tool_def.name] = tool_def

    def get(self, name: str) -> ToolDef | None:
        """Return a tool definition by name."""
        return self._tools.get(name)

    def list_all(self) -> list[ToolDef]:
        """Return all registered tool definitions."""
        return list(self._tools.values())

    def call(self, name: str, **kwargs: Any) -> Any:
        """Invoke a tool by name, forwarding kwargs."""
        tool = self.get(name)
        if tool is None:
            raise ValueError(f"Unknown tool: {name!r}")
        return tool.func(**kwargs)


# --------------------------------------------------------------------------


def tool(
    name: str,
    description: str = "",
    schema: dict | None = None,
) -> Callable[[F], F]:
    """Decorator to register a function as an MMI tool.

    Parameters
    ----------
    name : str
        Unique tool identifier.
    description : str
        Human-readable description.
    schema : dict, optional
        JSON Schema for parameters.

    Example
    -------
    @tool(name="search", description="Search the web")
    async def search(query: str) -> str:
        ...

    The decorated function is immediately registered in the global registry.
    """

    def decorator(func: F) -> F:
        registry = ToolRegistry.get_instance()
        registry.register(
            ToolDef(
                name=name,
                description=description,
                schema=schema or {},
                func=func,
            )
        )
        return func

    return decorator


# --------------------------------------------------------------------------


def discover_builtin_tools() -> None:
    """Auto-discover and register all tools decorated with @tool.

    Call once at startup.  Tools defined in other modules are registered
    as a side-effect of module import; this function is a hook for any
    additional discovery logic if needed.
    """
    # At this point all modules using @tool should already be imported,
    # so the registry is pre-populated.  This function exists as an
    # extension point for future plug-in scanning.
    pass
