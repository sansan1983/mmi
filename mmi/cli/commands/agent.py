"""mmi agent — 管理 Agent（列表/调用）。"""

from __future__ import annotations

from mmi.agent.builtin import CodeReviewAgent, DocAgent  # noqa: F401
from mmi.agent.modes import ThinkingMode as TM
from mmi.agent.orchestrator import Orchestrator
from mmi.agent.registry import AgentMeta, AgentRegistry
from mmi.cli import ensure_mmi_home


def _register_builtin_agents(reg) -> None:
    """把内置 Agent 注册到 registry（幂等，重复注册 ValueError 被吞）。"""
    try:
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
    except ValueError:
        pass
    try:
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
    except ValueError:
        pass


def cmd_agent(args, mgr) -> int:
    ensure_mmi_home()
    sub = getattr(args, "agent_cmd", None)
    if sub is None:
        print("usage: mmi agent {list|invoke}")
        return 1

    reg = AgentRegistry.get_instance()
    _register_builtin_agents(reg)

    if sub == "list":
        metas = reg.list_all(tag=getattr(args, "tag", None))
        if not metas:
            print("未注册任何 Agent")
            return 0
        print(f"已注册 {len(metas)} 个 Agent:\n")
        for m in metas:
            tags = ",".join(m.tags) if m.tags else "-"
            print(f"  [{m.agent_id:14s}] {m.name:14s}  v{m.version}  ({m.description})")
            print(f"      tags: {tags}  builtin: {m.builtin}")
        return 0

    if sub == "invoke":
        agent_id = args.agent_id
        agent_cls = reg.match(agent_id)
        if agent_cls is None:
            print(f"[!] Agent {agent_id!r} 未注册")
            return 1
        try:
            orch = Orchestrator(manager=mgr, llm=mgr.llm)
        except Exception as e:
            print(f"[!] Orchestrator 初始化失败: {e}")
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
            print(f"[!] 调用失败: {e}")
            return 1

    print(f"unknown agent subcommand: {sub}")
    return 1