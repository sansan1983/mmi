"""tests/test_context.py — context 模块测试。

测试 mmi.core.context 的核心功能：
- build_context() 基本构建
- compose_sections() 分块组合
- flatten_sections() 扁平化
- build_context_detailed() 详细版
"""

from __future__ import annotations

import inspect


class TestContextBasic:
    """基础功能测试"""

    def test_build_context_import(self):
        """验证 context 模块可导入"""
        from mmi.core import context
        assert hasattr(context, 'build_context')

    def test_compose_sections_import(self):
        """验证 compose_sections 可导入"""
        from mmi.core.context import compose_sections
        assert callable(compose_sections)

    def test_flatten_sections_import(self):
        """验证 flatten_sections 可导入"""
        from mmi.core.context import flatten_sections
        assert callable(flatten_sections)


class TestComposeSections:
    """compose_sections 功能测试"""

    def test_compose_sections_signature(self):
        """验证 compose_sections 签名"""
        from mmi.core.context import compose_sections
        sig = inspect.signature(compose_sections)
        assert len(sig.parameters) >= 3  # 至少3个参数

    def test_flatten_sections_signature(self):
        """验证 flatten_sections 签名"""
        from mmi.core.context import flatten_sections
        sig = inspect.signature(flatten_sections)
        assert len(sig.parameters) >= 1


class TestBuildContext:
    """build_context 功能测试"""

    def test_build_context_signature(self):
        """验证 build_context 签名"""
        from mmi.core.context import build_context
        sig = inspect.signature(build_context)
        assert len(sig.parameters) >= 3  # 至少3个参数

    def test_build_context_detailed_is_exposed(self):
        """P9.5 修复:build_context_detailed 已在 mmi/core/__init__.py:9 导出,
        旧测试 try/except + pytest.skip 完全是死代码 —— test_loader.py 与
        test_memory.py 都直接调用它,确认存在。"""
        from mmi.core.context import build_context_detailed
        assert callable(build_context_detailed)

    def test_context_module_has_core_functions(self):
        """验证 context 模块包含核心函数"""
        from mmi.core import context
        assert hasattr(context, 'build_context')
        assert hasattr(context, 'build_context_detailed')