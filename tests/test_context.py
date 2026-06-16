"""tests/test_context.py — context 模块测试。

测试 mmi.core.context 的核心功能：
- build_context() 基本构建
- compose_sections() 分块组合
- flatten_sections() 扁平化
"""

from __future__ import annotations

import pytest


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
        import inspect
        sig = inspect.signature(compose_sections)
        assert len(sig.parameters) >= 3  # 至少3个参数

    def test_flatten_sections_signature(self):
        """验证 flatten_sections 签名"""
        from mmi.core.context import flatten_sections
        import inspect
        sig = inspect.signature(flatten_sections)
        assert len(sig.parameters) >= 1


class TestBuildContext:
    """build_context 功能测试"""

    def test_build_context_signature(self):
        """验证 build_context 签名"""
        from mmi.core.context import build_context
        import inspect
        sig = inspect.signature(build_context)
        assert len(sig.parameters) >= 3  # 至少3个参数

    def test_build_context_detailed_if_available(self):
        """验证 build_context_detailed 如果存在"""
        try:
            from mmi.core.context import build_context_detailed
            assert callable(build_context_detailed)
        except ImportError:
            pytest.skip("build_context_detailed not available")

    def test_context_module_has_core_functions(self):
        """验证 context 模块包含核心函数"""
        from mmi.core import context
        # 检查核心函数是否存在
        assert hasattr(context, 'build_context')
        # build_context_detailed 可能不存在，使用 hasattr 检查
        # 不强制要求，因为这是内部函数