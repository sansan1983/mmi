"""mmi.core.gc_daemon —— 后台 GC daemon（单例，后台线程）。

设计：
  - 单例 DaemonGC，进程生命周期内只启动一次线程
  - 首次 chat() 时懒启动（不在模块 import 时触发，保持冷启动速度）
  - 两种触发模式：
      1. 次数触发：每 N 次 chat() 检查一次（通过 EventBus chat.done 计数）
      2. 定时触发：每小时一次（后台线程 sleep，精度不高但够用）
  - 所有异常在 daemon 内吞掉（不污染主流程）
  - 与手动 mmi gc 完全兼容：daemon 只清理 trash/zombie，cold 留给手动 gc
"""

from __future__ import annotations

import atexit
import contextlib
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass

log = logging.getLogger(__name__)

__all__ = ["start_gc_daemon", "GcDaemonConfig", "DaemonGC", "_get_gc_daemon"]


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

DEFAULT_CHAT_INTERVAL = 10   # 每 N 次 chat 触发一次 GC 检查
DEFAULT_SLEEP_SECONDS = 3600  # 定时触发：每小时


@dataclass
class GcDaemonConfig:
    """后台 GC 配置（可序列化，供 config.toml 持久化）。"""

    enabled: bool = True          # 是否启用后台 GC
    chat_interval: int = DEFAULT_CHAT_INTERVAL  # 每 N 次 chat 触发一次
    sleep_seconds: int = DEFAULT_SLEEP_SECONDS  # 定时触发间隔（秒）

    @classmethod
    def from_dict(cls: type[GcDaemonConfig], d: dict) -> GcDaemonConfig:
        return cls(
            enabled=bool(d.get("enabled", True)),
            chat_interval=int(d.get("chat_interval", DEFAULT_CHAT_INTERVAL)),
            sleep_seconds=int(d.get("sleep_seconds", DEFAULT_SLEEP_SECONDS)),
        )

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "chat_interval": self.chat_interval,
            "sleep_seconds": self.sleep_seconds,
        }


# ---------------------------------------------------------------------------
# 单例 DaemonGC
# ---------------------------------------------------------------------------

class DaemonGC:
    """后台 GC 单例（线程安全单例模式）。

    属性：
        config: 当前配置
        gc_func: 实际执行的 GC 函数（可注入，供测试 mock）
    """

    _instance: DaemonGC | None = None
    _lock_init = threading.Lock()

    def __init__(
        self,
        config: GcDaemonConfig | None = None,
        gc_func: Callable | None = None,
    ) -> None:
        self.config = config or GcDaemonConfig()
        self._gc_func = gc_func or self._default_gc
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._chat_count = 0
        self._lock = threading.Lock()

    @classmethod
    def get_instance(cls: type[DaemonGC]) -> DaemonGC:
        if cls._instance is None:
            with cls._lock_init:
                if cls._instance is None:
                    cfg = cls._load_config()
                    cls._instance = cls(config=cfg)
        return cls._instance

    @classmethod
    def _load_config(cls) -> GcDaemonConfig:
        """从 config.toml 读取配置（失败走默认）。"""
        try:
            from . import config as cfg_mod
            cfg_data = cfg_mod.load_config()
            daemon_cfg = cfg_data.get("gc_daemon", {})
            if isinstance(daemon_cfg, dict):
                return GcDaemonConfig.from_dict(daemon_cfg)
        except Exception:
            pass
        return GcDaemonConfig()

    @classmethod
    def update_config(cls: type[GcDaemonConfig], cfg: GcDaemonConfig) -> None:
        """更新配置并持久化到 config.toml。"""
        try:
            from . import config as cfg_mod
            full = cfg_mod.load_config()
            full["gc_daemon"] = cfg.to_dict()
            cfg_mod.save_config(full)
        except Exception:
            pass
        if cls._instance is not None:
            cls._instance.config = cfg

    def _default_gc(self) -> None:
        """默认 GC：只扫 trash 超期 + zombie，不动 cold。"""
        try:
            from . import gc as gc_mod
            gc_mod.gc_trash(dry_run=False)
            gc_mod.gc_zombies(dry_run=False)
        except Exception:
            pass  # daemon 内所有异常静默

    # ----- 公开 API（Manager 调） -------------------------------------------

    def on_chat_done(self) -> None:
        """每次 chat 完成时调用（Manager.chat 末尾）。"""
        if not self.config.enabled:
            return
        with self._lock:
            self._chat_count += 1
            count = self._chat_count
        if count >= self.config.chat_interval:
            with self._lock:
                self._chat_count = 0
            self._run_gc_once()

    def _run_gc_once(self) -> None:
        """单次 GC 调用（在后台线程内或直接在调用线程内均可）。"""
        with contextlib.suppress(Exception):
            self._gc_func()

    # ----- 线程管理 ---------------------------------------------------------

    def ensure_started(self) -> None:
        """确保后台线程已启动（幂等）。"""
        if not self.config.enabled:
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="mmi-gc-daemon",
            daemon=True,
        )
        self._thread.start()
        log.info("GC daemon started (interval=%d chat, sleep=%ds)",
                 self.config.chat_interval, self.config.sleep_seconds)
        atexit.register(self.stop)

    def stop(self) -> None:
        """停止后台线程。"""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
        log.info("GC daemon stopped")

    def _run_loop(self) -> None:
        """后台线程主循环（sleep + 定时触发 GC）。"""
        sleep = self.config.sleep_seconds
        while not self._stop_event.wait(timeout=sleep):
            self._run_gc_once()


# ---------------------------------------------------------------------------
# 模块级便利函数（延迟解析，兼容测试单例重置）
# ---------------------------------------------------------------------------

def _get_gc_daemon() -> DaemonGC:
    """返回全局 gc_daemon 实例（每次调用实时解析，兼容测试重置）。"""
    return DaemonGC.get_instance()



def start_gc_daemon() -> None:
    """启动 GC daemon（幂等，在 Manager 初始化时调用一次即可）。"""
    _get_gc_daemon().ensure_started()
