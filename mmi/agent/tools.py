"""Tool registry with @tool decorator and auto-discovery."""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, ClassVar, TypeVar

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
    func: Callable[..., Any] = field(default=None, repr=False)  # type: ignore[assignment]


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
    """3.6 改进:Auto-discover and register all tools decorated with @tool.

    实现:遍历 mmi.agent.builtin 包的成员,import 它们触发 @tool 副作用。
    之前是空 pass,3.6 改为真正 import。
    """
    import importlib
    import pkgutil

    import mmi.agent.builtin as _builtin_pkg

    for mod_info in pkgutil.iter_modules(_builtin_pkg.__path__):
        mod_name = f"mmi.agent.builtin.{mod_info.name}"
        # 跳过内置 agent 类(它们不是工具)
        if mod_name.endswith(".agents"):
            continue
        with contextlib.suppress(Exception):
            importlib.import_module(mod_name)
