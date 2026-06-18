"""mmi agent — 管理 Agent（列表/调用）。"""

from __future__ import annotations

import contextlib

from mmi.agent.builtin import CodeReviewAgent, DocAgent  # noqa: F401
from mmi.agent.modes import ThinkingMode as TM  # noqa: N817
from mmi.agent.orchestrator import Orchestrator
from mmi.agent.registry import AgentMeta, AgentRegistry
from mmi.cli import dispatch_subcommand, ensure_mmi_home
from mmi.core import i18n


def _register_builtin_agents(reg) -> None:
    """把内置 Agent 注册到 registry（幂等，重复注册 ValueError 被吞）。"""
    with contextlib.suppress(ValueError):
        reg.register(
            AgentMeta(
                agent_id="code_review",
                name="Code Review",
                description="审查/重构/审计源码",
                tags=["code", "review", "security", "audit"],
                version="0.1.0",
                builtin=True,
            ),
            CodeReviewAgent,
        )
    with contextlib.suppress(ValueError):
        reg.register(
            AgentMeta(
                agent_id="doc",
                name="Doc",
                description="生成文档/翻译",
                tags=["doc", "docstring", "translation"],
                version="0.1.0",
                builtin=True,
            ),
            DocAgent,
        )


def cmd_agent(args, mgr) -> int:
    ensure_mmi_home()
    return dispatch_subcommand(
        args,
        "agent_cmd",
        {
            "list": lambda: _agent_list(args),
            "invoke": lambda: _agent_invoke(args, mgr),
        },
        usage="usage: mmi agent {list|invoke}",
    )


def _agent_list(args) -> int:
    reg = AgentRegistry.get_instance()
    _register_builtin_agents(reg)
    metas = reg.list_all(tag=getattr(args, "tag", None))
    if not metas:
        print(i18n.t("agent.list.empty"))
        return 0
    print(i18n.t("agent.list.header", count=len(metas)))
    for m in metas:
        tags = ",".join(m.tags) if m.tags else "-"
        print(i18n.t("agent.list.entry", agent_id=m.agent_id, name=m.name, version=m.version, description=m.description, tags=tags, builtin=m.builtin))
    return 0


def _agent_invoke(args, mgr) -> int:
    reg = AgentRegistry.get_instance()
    _register_builtin_agents(reg)
    agent_id = args.agent_id
    agent_cls = reg.match(agent_id)
    if agent_cls is None:
        print(i18n.t("agent.invoke.not_registered", id=agent_id))
        return 1
    try:
        orch = Orchestrator(manager=mgr, llm=mgr.llm)
    except Exception as e:
        print(i18n.t("agent.invoke.orchestrator_failed", error=str(e)))
        return 1
    mode_str = getattr(args, "mode", None)
    mode = TM[mode_str] if mode_str else None
    try:
        reply = orch.chat_legacy(
            session_id=args.session,
            user_message=args.message,
            mode=mode,
        )
        print(reply)
        return 0
    except Exception as e:
        print(i18n.t("agent.invoke.failed", error=str(e)))
        return 1
