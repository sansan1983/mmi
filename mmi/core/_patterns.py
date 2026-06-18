"""mmi.core._patterns —— 跨模块共享的轻量模式。

集中放 Singleton 基类,避免 7+ 个模块各自重复 get_instance() 模板
以及引入非线程安全的懒初始化 bug。
"""

from __future__ import annotations

import threading
from typing import ClassVar


class Singleton:
    """线程安全单例基类(双重检查锁定 DCL)。

    用法:
        class Foo(Singleton):
            def __init__(self, x: int) -> None:
                self.x = x    # 幂等赋值即可

        Foo.get_instance()    # -> Foo 唯一实例
        Foo(42).get_instance()  # 也会返回唯一实例(首次走 __init__(42))
        Foo.reset_instance()  # 仅测试用

    约定:子类 __init__ 必须幂等(简单字段赋值,无副作用),
    重复 get_instance() 不会重新调 __init__。

    已知限制:首次创建时 Python 会用构造时的 *args/**kwargs 调 __init__,
    之后 get_instance() 永远不调 __init__(这是单例正确语义)。
    """

    _instances: ClassVar[dict[type, object]] = {}
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __new__(cls, *args: object, **kwargs: object) -> object:
        instances = Singleton._instances
        if cls in instances:
            return instances[cls]
        with Singleton._lock:
            if cls not in instances:
                instances[cls] = super().__new__(cls)
        return instances[cls]

    @classmethod
    def get_instance(cls: type[object]) -> object:
        """返回唯一实例(首次按构造参数创建,之后直接返回)。"""
        return cls()

    @classmethod
    def reset_instance(cls: type[object]) -> None:
        """清空单例缓存(仅供测试夹具使用)。"""
        Singleton._instances.pop(cls, None)
