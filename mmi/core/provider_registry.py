"""mmi.core.provider_registry —— 自定义 Provider 插件发现与注册。

P4-1: 用户可将自定义 LLM Provider 作为 Python 插件放到 ``~/.mmi/providers/`` 目录下，
MMI 自动发现、加载并注册。

插件协议
--------
每个插件是一个 ``.py`` 文件，必须导出一个继承 ``LLMProvider`` 的类，
并设置 ``name`` 类属性为唯一标识：

.. code-block:: python

    # ~/.mmi/providers/my_provider.py
    from mmi.core.llm import LLMProvider, LLMError, Classification

    class MyProvider(LLMProvider):
        name = "my-provider"

        def __init__(self, api_key: str, model: str = "my-model-v1", **kwargs):
            self._api_key = api_key
            self._model = model

        def chat(self, messages, *, max_tokens=4096, temperature=0.7):
            ...

        def classify(self, prompt, *, options):
            ...

配置
----
在 ``~/.mmi/config.toml`` 中指定：

.. code-block:: toml

    [llm]
    provider = "my-provider"
    api_key = "sk-..."
    model = "my-model-v1"
"""

from __future__ import annotations

import importlib.util
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Type

from mmi.core.paths import get_root
from mmi.core.llm import LLMProvider


@dataclass
class RegisteredProvider:
    """A discovered and registered custom provider plugin."""

    name: str
    """Unique provider identifier (matches ``LLMProvider.name``)."""

    cls: Type[LLMProvider]
    """The LLMProvider subclass."""

    source_file: str
    """Path to the plugin file."""

    config_schema: dict[str, Any] = field(default_factory=dict)
    """Optional JSON Schema describing required config keys."""

    @property
    def description(self) -> str:
        doc = self.cls.__doc__
        return doc.strip() if doc else f"Custom provider: {self.name}"


class ProviderRegistry:
    """Discovers, loads, and manages custom Provider plugins.

    Singleton access via ``get_instance()``.  Thread-safe.

    Usage::

        registry = ProviderRegistry.get_instance()
        registry.discover()  # scan ~/.mmi/providers/

        cls = registry.get_provider_class("my-provider")
        if cls:
            instance = cls(api_key="sk-...", model="v1")
            reply = instance.chat(messages)
    """

    _instance: ClassVar[ProviderRegistry | None] = None

    def __init__(self, *, providers_dir: Path | None = None) -> None:
        self._providers: dict[str, RegisteredProvider] = {}
        self._lock = threading.RLock()
        self._providers_dir = providers_dir or (get_root() / "providers")
        self._providers_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_instance(cls) -> ProviderRegistry:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """For testing only."""
        cls._instance = None

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self) -> list[str]:
        """Scan ``~/.mmi/providers/`` for ``.py`` plugin files.

        Returns
        -------
        list[str]
            Names of newly discovered providers.
        """
        newly_found: list[str] = []

        with self._lock:
            for path in sorted(self._providers_dir.glob("*.py")):
                name_hint = path.stem
                try:
                    loaded = self._load_plugin(path)
                    if loaded and loaded.name not in self._providers:
                        self._providers[loaded.name] = loaded
                        newly_found.append(loaded.name)
                except Exception:
                    # Skip broken plugins silently
                    pass

        return newly_found

    def _load_plugin(self, path: Path) -> RegisteredProvider | None:
        """Load a single plugin file and extract the LLMProvider subclass.

        Returns
        -------
        RegisteredProvider | None
            The registered provider, or None if no valid class found.
        """
        spec = importlib.util.spec_from_file_location(
            f"_mmi_plugin_{path.stem}", str(path)
        )
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        # Temporarily add to sys.modules so relative imports work
        old_module = sys.modules.get(module.__name__)
        try:
            sys.modules[module.__name__] = module
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(module.__name__, None)
            if old_module is not None:
                sys.modules[module.__name__] = old_module
            return None
        finally:
            # Clean up from sys.modules to avoid stale references
            if old_module is None:
                sys.modules.pop(module.__name__, None)

        # Find LLMProvider subclasses in the module
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, LLMProvider)
                and attr is not LLMProvider
                and hasattr(attr, "name")
                and isinstance(attr.name, str)
                and attr.name.strip()
            ):
                return RegisteredProvider(
                    name=attr.name,
                    cls=attr,
                    source_file=str(path),
                )

        return None

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, registered: RegisteredProvider) -> None:
        """Manually register a provider (e.g. from config)."""
        with self._lock:
            self._providers[registered.name] = registered

    def unregister(self, name: str) -> None:
        """Remove a registered provider."""
        with self._lock:
            self._providers.pop(name, None)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_provider_class(self, name: str) -> Type[LLMProvider] | None:
        """Return the LLMProvider subclass for *name*, or None."""
        reg = self._providers.get(name)
        return reg.cls if reg else None

    def list_registered(self) -> list[RegisteredProvider]:
        """Return all registered custom providers."""
        with self._lock:
            return list(self._providers.values())

    def list_names(self) -> list[str]:
        """Return all registered provider names."""
        with self._lock:
            return list(self._providers.keys())

    def has_provider(self, name: str) -> bool:
        """Check if a provider is registered."""
        return name in self._providers
