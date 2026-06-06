"""mmi CLI 入口（Phase 1：CLI 最小闭环）。

子命令：
  mmi --version                       # 版本（双语）
  mmi --lang <zh-CN|en-US> ...        # 语言切换
  mmi new [title]                     # 新建会话（可选标题）
  mmi list [--limit N]                # 列最近 N 条会话（默认 10）
  mmi chat <session_id>               # 进入 REPL：q 退出，Ctrl+C 也退出
  mmi archive <session_id>            # 归档到 trash
  mmi delete <session_id>             # 硬删

所有用户可见字符串走 t() i18n（ARCHITECTURE.md §3.5.7）。

设计原则：
  - UI ≠ 推理 / 显示 ≠ 发送（ARCHITECTURE.md §2）
  - 不直接读会话文件，全部走 SessionManager
  - 错误信息走 stderr（异常退出码非 0），成功输出走 stdout
"""

import argparse
import sys
import json
from pathlib import Path

# 允许从仓库根直接 `python mmi/cli.py` 运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Windows console 默认 GBK 会把 UTF-8 中文打成乱码；强制重配 stdout/stderr。
# 必须在 import i18n 之前，否则 t() 内部的 print 也会乱。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        # 旧版 Python / 重定向到文件时可能没 reconfigure；忽略即可
        pass

from mmi.core import i18n  # noqa: E402
from mmi.core import manager as mgr_module  # noqa: E402
from mmi.core import paths  # noqa: E402
from mmi.core import storage  # noqa: E402
from mmi import __product_name__, __version__  # noqa: E402

VERSION = __version__
DEFAULT_LIMIT = 10

# 仓库根目录（cli.py 上两级：mmi/cli.py -> mmi/ -> REPO_ROOT）。
# 给 tui 子命令定位 tui-ts/dist/mmi-tui.js 用。
REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mmi",
        description=f"{__product_name__} — 带记忆的智能体主板（Context Trim）",
    )
    parser.add_argument(
        "--lang",
        choices=i18n.SUPPORTED_LANGS,
        default=None,
        help="界面语言（默认根据 LANG 环境变量自动选择，可显式覆盖）",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="显示版本并退出",
    )

    sub = parser.add_subparsers(dest="command")

    # new
    p_new = sub.add_parser("new", help="新建会话（可选标题参数）")
    p_new.add_argument(
        "title",
        nargs="?",
        default=None,
        help="会话标题（可省略，新建后再改名）",
    )

    # list
    p_list = sub.add_parser("list", help="列出最近会话")
    p_list.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        metavar="N",
        help=f"最多显示几条（默认 {DEFAULT_LIMIT}）",
    )
    p_list.add_argument(
        "--state",
        choices=["active", "warm", "cold", "zombie", "all"],
        default="all",
        help="按状态过滤（默认 all）",
    )

    # chat
    p_chat = sub.add_parser("chat", help="继续指定会话")
    p_chat.add_argument("session_id", help="要继续的会话 ID（ULID）")
    p_chat.add_argument(
        "--inspect",
        action="store_true",
        help="启动前预览 prompt 诊断信息（不进入对话 loop）",
    )

    # archive
    p_archive = sub.add_parser("archive", help="归档会话到 trash")
    p_archive.add_argument("session_id", help="要归档的会话 ID")

    # delete
    p_delete = sub.add_parser("delete", help="硬删会话（不可恢复）")
    p_delete.add_argument("session_id", help="要删除的会话 ID")

    # gc
    p_gc = sub.add_parser("gc", help="清理 trash 目录中超期的会话")
    p_gc.add_argument(
        "--ttl-days",
        type=int,
        default=7,
        metavar="N",
        help="trash TTL（天），超过此时间的会话会被删（默认 7）",
    )
    p_gc.add_argument(
        "--dry-run",
        action="store_true",
        help="只列出会被删的会话，不真删",
    )
    p_gc.add_argument(
        "--gc-only",
        choices=["cold", "zombie", "trash", "all"],
        default="all",
        help="只跑某一层 GC（默认 all）",
    )

    # tui
    p_tui = sub.add_parser("tui", help="启动 TUI（TypeScript + Ink，通过 Python IPC 通信）")
    p_tui.add_argument(
        "--build",
        action="store_true",
        help="强制重新构建 tui-ts 的 TypeScript bundle（首次启动会自动构建）",
    )

    # doctor
    sub.add_parser("doctor", help="系统诊断 — 检查模块/会话/文件系统/heat一致性/GC状态")

    # stat
    sub.add_parser("stat", help="显示会话统计（总数/各状态/总大小）")

    # export
    p_export = sub.add_parser("export", help="导出会话为 JSON 或 Markdown")
    p_export.add_argument("session_id", help="要导出的会话 ID")
    p_export.add_argument("output", help="输出文件路径（.json / .md）")
    p_export.add_argument(
        "--format",
        choices=["json", "markdown"],
        default=None,
        help="导出格式（默认根据文件扩展名自动推断）",
    )
    p_export.add_argument(
        "--compact",
        action="store_true",
        help="JSON 不缩进（减少文件大小）",
    )

    # mmi rename <session_id> <title>
    p_rename = sub.add_parser("rename", help="重命名会话标题")
    p_rename.add_argument("session_id", help="会话 ID")
    p_rename.add_argument("title", help="新标题")
    p_rename.add_argument("-f", "--force", action="store_true",
        help="允许覆盖已有标题（跳过重复检查）")

    # mmi info <session_id>

    # mmi inspect <session_id> [--text "..."]
    p_inspect = sub.add_parser("inspect", help="预览当前上下文裁剪结果（诊断用，不调 LLM）")
    p_inspect.add_argument("session_id", help="会话 ID")
    p_inspect.add_argument("--text", default=None, help="模拟用户输入（不传则用空字符串）")
    p_info = sub.add_parser("info", help="显示会话详细信息")
    p_info.add_argument("session_id", help="会话 ID")

    # update
    p_update = sub.add_parser("update", help="更新会话热度（access_count / last_access / heat），不产生对话")
    p_update.add_argument("session_id", help="要更新的会话 ID")

    # mmi memory search <query>
    p_memory = sub.add_parser("memory", help="跨会话记忆检索")
    p_memory_sub = p_memory.add_subparsers(dest="memory_cmd")
    p_memory_search = p_memory_sub.add_parser("search", help="语义检索历史记忆")
    p_memory_search.add_argument("query", nargs="+", help="查询关键词（多个词拼成一句话）")
    p_memory_search.add_argument("-k", "--top-k", type=int, default=5,
                                  help="返回 top-K 结果（默认 5）")
    p_memory_sub.add_parser("count", help="显示当前记忆总数")
    p_memory_clear = p_memory_sub.add_parser("clear", help="清空所有记忆（危险,需 --yes 确认）")
    p_memory_clear.add_argument("--yes", action="store_true", help="跳过确认")

    # mmi config —— 配置 LLM provider / key / model
    p_config = sub.add_parser("config", help="配置 LLM(provider / api_key / model)")
    p_config_sub = p_config.add_subparsers(dest="config_cmd")
    p_config_sub.add_parser("show", help="显示当前 LLM 配置")
    p_config_wizard = p_config_sub.add_parser("wizard", help="交互式配置向导")
    p_config_wizard.add_argument("--provider", help="跳过 provider 选择(直接传 provider id)")
    p_config_wizard.add_argument("--api-key", help="跳过 api_key 提示(直接传)")
    p_config_wizard.add_argument("--model", help="跳过模型选择(直接传模型 id)")
    p_config_wizard.add_argument("--no-fetch", action="store_true",
                                  help="不拉模型列表,直接用 --model")

    # mmi agent —— 3.9 列出/调用已注册 Agent
    p_agent = sub.add_parser("agent", help="管理 Agent(列表/调用)")
    p_agent_sub = p_agent.add_subparsers(dest="agent_cmd")
    p_agent_list = p_agent_sub.add_parser("list", help="列出所有已注册 Agent")
    p_agent_list.add_argument("--tag", help="按 tag 过滤")
    p_agent_invoke = p_agent_sub.add_parser("invoke", help="直接调指定 Agent")
    p_agent_invoke.add_argument("agent_id", help="Agent ID(如 code_review)")
    p_agent_invoke.add_argument("message", help="用户消息")
    p_agent_invoke.add_argument("--session", required=True, help="目标 session_id")
    p_agent_invoke.add_argument("--mode", choices=["STANDARD", "BRAINSTORM", "AUDIT"], help="思维模式")

    # mmi skill —— 3.12 列出/创建 Skill
    p_skill = sub.add_parser("skill", help="管理 Skill(列表/创建/搜索)")
    p_skill_sub = p_skill.add_subparsers(dest="skill_cmd")
    p_skill_sub.add_parser("list", help="列出所有 Skill")
    p_skill_search = p_skill_sub.add_parser("search", help="按关键词搜索 Skill")
    p_skill_search.add_argument("query", help="搜索关键词")
    p_skill_create = p_skill_sub.add_parser("create", help="创建新 Skill")
    p_skill_create.add_argument("skill_id", help="Skill 唯一 ID")
    p_skill_create.add_argument("name", help="Skill 名称")
    p_skill_create.add_argument("content", help="Skill 内容(prompt/描述)")
    p_skill_create.add_argument("--apply-scene", default="", help="使用场景")
    p_skill_create.add_argument("--tags", default="", help="逗号分隔的 tags")

    return parser


# ---------------------------------------------------------------------------
# 子命令实现
# ---------------------------------------------------------------------------


def cmd_new(args, mgr) -> int:
    # Round 0.10: auto-inject MMI_HOME for fusion worktree isolation
    import os
    from pathlib import Path
    if "MMI_HOME" not in os.environ:
        os.environ["MMI_HOME"] = str(Path.home() / ".mmi-fusion")
    title = args.title or "untitled"
    sid = mgr.create(title=title)
    print(i18n.t("new.success", session_id=sid))
    print(i18n.t("new.success.hint", session_id=sid))
    return 0


    # Round 0.13: auto-inject MMI_HOME for fusion worktree isolation
    import os
    from pathlib import Path
    if "MMI_HOME" not in os.environ:
        os.environ["MMI_HOME"] = str(Path.home() / ".mmi-fusion")

def cmd_list(args, mgr) -> int:
    sessions = mgr.list_sessions(limit=args.limit)
    if args.state != "all":
        sessions = [s for s in sessions if s.state == args.state]
    sessions = mgr.list_sessions(limit=args.limit)
    if not sessions:
        print(i18n.t("list.empty"))
        return 0
    print(i18n.t("list.title"))
    if args.state != "all":
        print("  [filter: state={}]".format(args.state))
    for i, s in enumerate(sessions, 1):
        # 简化：直接按 key 渲染，title 为空时用 unnamed 版
        if s.title:
            print(i18n.t("list.entry", index=i, title=s.title, heat=s.heat, state=s.state))
        else:
            print(i18n.t("list.entry.unnamed", index=i, heat=s.heat, state=s.state))
    return 0


    # Round 0.13: auto-inject MMI_HOME for fusion worktree isolation
    import os
    from pathlib import Path
    if "MMI_HOME" not in os.environ:
        os.environ["MMI_HOME"] = str(Path.home() / ".mmi-fusion")

def cmd_stat(args, mgr) -> int:
    """显示会话统计（总数/各状态占比/总大小）。"""
    from collections import Counter
    from mmi.core import storage

    all_sids = storage.list_session_ids()
    trash_sids = storage.list_trash_ids()
    all_meta = [storage.read_meta(sid) for sid in all_sids]
    state_counts = Counter(s.state for s in all_meta)
    total_size = sum(
        storage.session_path(sid).stat().st_size
        for sid in all_sids
        if storage.session_path(sid).exists()
    )
    total = len(all_meta)
    print("MMI Statistics")
    print("  active:    {:4d}".format(total))
    for state in ["active", "warm", "cold", "zombie"]:
        cnt = state_counts.get(state, 0)
        pct = cnt / total * 100 if total else 0
        print("    {}: {:4d} ({:.1f}%)".format(state, cnt, pct))
    print("  trash:     {:4d}".format(len(trash_sids)))
    print("  total size: {:.2f} MB".format(total_size / 1024 / 1024))
    return 0


def cmd_chat(args, mgr) -> int:
    """继续指定会话的聊天 loop。"""
    # Round 0.12: auto-inject MMI_HOME for fusion worktree isolation
    import os
    from pathlib import Path
    if "MMI_HOME" not in os.environ:
        os.environ["MMI_HOME"] = str(Path.home() / ".mmi-fusion")

    sid = args.session_id
    try:
        mgr.get(sid)
    except storage.SessionNotFound:
        print(i18n.t("chat.unknown_session", session_id=sid), file=sys.stderr)
        return 1

    # Round 0.12: --inspect mode: preview prompt before entering loop
    if args.inspect:
        from mmi.core import context as _loader
        try:
            mgr.get(sid)
        except Exception:
            print(f"session not found: {sid}", file=sys.stderr)
            return 1
        meta = storage.read_meta(sid)
        config = _loader.LoaderConfig()
        # Use same API as cmd_inspect: build_context_detailed + compose_messages
        ctx = _loader.build_context_detailed(sid, "", config)
        messages = _loader.compose_messages(ctx, "", config, language=args.lang or "zh-CN")
        sys_msg = next((m for m in messages if m.get("role") == "system"), {})
        sys_content = sys_msg.get("content", "") or ""
        print("=" * 60)
        print(f"mmi chat --inspect  |  session={sid}")
        print("=" * 60)
        print(f"  title          : {meta.title}")
        print(f"  state          : {meta.state}")
        print(f"  recent_turns   : {len(ctx.recent_turns)} pairs")
        print(f"  hit_paragraphs : {len(ctx.hit_turns)} kept")
        print(f"  token_limit    : {config.max_tokens}")
        print(f"  tokens used    : {ctx.estimated_tokens} ({ctx.estimated_tokens/config.max_tokens*100:.1f}%)")
        print()
        print("[system prompt]")
        print(f"  {len(sys_content)} chars  |  {_loader.estimate_tokens([sys_msg])} tokens")
        print("  %s" % sys_content[:200])
        print()
        if ctx.estimated_tokens > config.max_tokens * 0.8:
            print(f"  [WARN] Within {int(config.max_tokens*0.8)} tokens (80%), consider compacting")
        else:
            print(f"  [OK] {config.max_tokens - ctx.estimated_tokens} tokens headroom")
        print()
        print(f"Use 'mmi chat {sid}' to start the conversation loop")
        return 0

    print(i18n.t("chat.welcome", session_id=sid))
    print(i18n.t("chat.echo_disabled"))
    print(i18n.t("chat.exit_hint"))
    print()

    try:
        while True:
            try:
                line = input(i18n.t("chat.prompt"))
            except EOFError:
                # Ctrl+D / pipe 输入结束
                print()
                break
            stripped = line.strip()
            if not stripped:
                continue
            if stripped in ("q", "quit", "exit"):
                break

            try:
                result = mgr.chat(sid, stripped)
            except storage.SessionNotFound:
                print(i18n.t("chat.session_trashed"))
                break
            # 注意：这里显示给用户的 ≠ 送进 LLM 的（Phase 3 走 loader 修剪）
            print(i18n.t("chat.assistant_said", content=result.reply))
            if result.trashed:
                print(i18n.t("chat.moved_to_trash", reason=result.trashed_reason))
            if result.title_updated:
                print(i18n.t("chat.title_updated"))
            if result.summary_updated:
                # 拿到最新 version
                try:
                    meta = storage.read_meta(sid)
                    print(i18n.t("chat.summary_updated", version=meta.summary_version))
                except storage.SessionNotFound:
                    pass
            if result.context_truncated:
                print(i18n.t("chat.context_truncated"))
            print()
    except KeyboardInterrupt:
        # Ctrl+C 优雅退出
        print()

    return 0


    # Round 0.13: auto-inject MMI_HOME for fusion worktree isolation
    import os
    from pathlib import Path
    if "MMI_HOME" not in os.environ:
        os.environ["MMI_HOME"] = str(Path.home() / ".mmi-fusion")

def cmd_export(args, mgr) -> int:
    """导出会话为 JSON 或 Markdown。"""
    try:
        sess = storage.read_session(args.session_id)
    except storage.SessionNotFound:
        print(f"session not found: {args.session_id}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"{e}", file=sys.stderr)
        return 1
    meta = sess.meta

    # Build export data
    data = {
        "session_id": meta.session_id,
        "title": meta.title,
        "agent_id": meta.agent_id,
        "created_at": str(meta.created_at),
        "updated_at": str(meta.updated_at),
        "last_access": str(meta.last_access),
        "access_count": meta.access_count,
        "heat": round(meta.heat, 4),
        "state": meta.state,
        "turns": [],
    }

    # Parse turns from body
    for line in sess.body.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("## "):
            role = "user"
            content = stripped[3:].strip()
        elif stripped.startswith("### "):
            role = "assistant"
            content = stripped[4:].strip()
        else:
            continue
        data["turns"].append({"role": role, "content": content})

    output = args.output
    if args.format == "json" or output.endswith(".json"):
        indent = None if args.compact else 2
        content_out = json.dumps(data, indent=indent, ensure_ascii=False)
        Path(output).write_text(content_out)
    else:  # markdown
        lines_md = [
            f"# {meta.title or 'Untitled Session'}",
            "",
            f"**Session ID**: `{meta.session_id}`  |  **Agent**: {meta.agent_id}  |  **State**: {meta.state}",
            f"**Created**: {meta.created_at.date()}  |  **Updated**: {meta.updated_at.date()}  |  **Heat**: {meta.heat:.4f}",
            "",
        ]
        for t in data["turns"]:
            lines_md.append(f"## {t['role'].capitalize()}")
            lines_md.append(t["content"])
            lines_md.append("")
        Path(output).write_text("\n".join(lines_md))

    print(f"exported {len(data['turns'])} turns to {output}")
    return 0


    sid = args.session_id
    # 先验证会话存在（否则会等到第一次 chat 才知道）
    try:
        mgr.get(sid)
    except mgr_module.SessionNotFound:
        print(i18n.t("chat.unknown_session", session_id=sid), file=sys.stderr)
        return 2

    print(i18n.t("chat.opened", session_id=sid))
    print(i18n.t("chat.echo_disabled"))
    print(i18n.t("chat.exit_hint"))
    print()

    try:
        while True:
            try:
                line = input(i18n.t("chat.prompt"))
            except EOFError:
                # Ctrl+D / pipe 输入结束
                print()
                break
            stripped = line.strip()
            if not stripped:
                continue
            if stripped in ("q", "quit", "exit"):
                break

            try:
                result = mgr.chat(sid, stripped)
            except storage.SessionNotFound:
                print(i18n.t("chat.session_trashed"))
                break
            # 注意：这里显示给用户的 ≠ 送进 LLM 的（Phase 3 走 loader 修剪）
            print(i18n.t("chat.assistant_said", content=result.reply))
            if result.trashed:
                print(i18n.t("chat.moved_to_trash", reason=result.trashed_reason))
            if result.title_updated:
                print(i18n.t("chat.title_updated"))
            if result.summary_updated:
                # 拿到最新 version
                try:
                    meta = storage.read_meta(sid)
                    print(i18n.t("chat.summary_updated", version=meta.summary_version))
                except storage.SessionNotFound:
                    pass
            if result.context_truncated:
                print(i18n.t("chat.context_truncated"))
            print()
    except KeyboardInterrupt:
        # Ctrl+C 优雅退出
        print()

    return 0


def cmd_archive(args, mgr) -> int:
    """归档指定会话到 trash。"""
    # Round 0.13: auto-inject MMI_HOME for fusion worktree isolation
    import os
    from pathlib import Path
    if "MMI_HOME" not in os.environ:
        os.environ["MMI_HOME"] = str(Path.home() / ".mmi-fusion")

    try:
        mgr.archive(args.session_id)
    except mgr_module.SessionNotFound:
        print(i18n.t("archive.unknown_session", session_id=args.session_id), file=sys.stderr)
        return 2
    print(i18n.t("archive.success", session_id=args.session_id))
    return 0


    # Round 0.13: auto-inject MMI_HOME for fusion worktree isolation
    import os
    from pathlib import Path
    if "MMI_HOME" not in os.environ:
        os.environ["MMI_HOME"] = str(Path.home() / ".mmi-fusion")

def cmd_delete(args, mgr) -> int:
    try:
        mgr.delete(args.session_id)
    except mgr_module.SessionNotFound:
        print(i18n.t("delete.unknown_session", session_id=args.session_id), file=sys.stderr)
        return 2
    print(i18n.t("delete.success", session_id=args.session_id))
    return 0


def _fmt_entry(entry):
    age = "{:.1f}".format(entry.age_days)
    reason = getattr(entry, 'reason', '') or ''
    mark = " [DEL]" if getattr(entry, 'deleted', False) else ""
    err = " [ERR: {}]".format(entry.error) if entry.error else ""
    base = "  {}  age={}d".format(entry.session_id, age)
    if reason:
        return base + "  " + reason + mark + err
    return base + mark + err


    # Round 0.13: auto-inject MMI_HOME for fusion worktree isolation
    import os
    from pathlib import Path
    if "MMI_HOME" not in os.environ:
        os.environ["MMI_HOME"] = str(Path.home() / ".mmi-fusion")

def cmd_gc(args, mgr) -> int:
    """三层 GC：cold/zombie/trash，支持 --gc-only 单独跑某一层。"""
    from mmi.core import gc as gc_module

    mode = args.gc_only
    ttl = args.ttl_days

    print(i18n.t("gc.title"))
    print("  ttl={}d  mode={}  dry-run={}".format(ttl, mode, args.dry_run))
    print()

    if mode == "all":
        report = gc_module.gc_all(ttl_days=ttl, dry_run=args.dry_run)
    elif mode == "cold":
        report = gc_module.gc_cold(cold_ttl_days=ttl, dry_run=args.dry_run)
    elif mode == "zombie":
        report = gc_module.gc_zombies(dry_run=args.dry_run)
    else:
        report = gc_module.gc_trash(ttl_days=ttl, dry_run=args.dry_run)

    if not report.entries:
        print(i18n.t("gc.empty"))
        return 0

    header = i18n.t("gc.dry_run") + " [{}]".format(mode) if args.dry_run else i18n.t("gc.title") + " [{}]:".format(mode)
    print(header)

    cold_ents = report.cold_entries
    if cold_ents:
        kept = sum(1 for e in cold_ents if not getattr(e, 'deleted', False))
        moved = sum(1 for e in cold_ents if getattr(e, 'deleted', False))
        print("\\n  [cold] {} total  kept={}  moved->trash={}".format(len(cold_ents), kept, moved))
        for e in cold_ents:
            print(_fmt_entry(e))

    zombie_ents = report.zombie_entries
    if zombie_ents:
        print("\\n  [zombie] {} total".format(len(zombie_ents)))
        for e in zombie_ents:
            print(_fmt_entry(e))

    trash_ents = report.trash_entries
    if trash_ents:
        print("\\n  [trash] {} total".format(len(trash_ents)))
        for e in trash_ents:
            print(_fmt_entry(e))

    if not args.dry_run:
        if report.deleted_count:
            print()
            print(i18n.t("gc.deleted", count=report.deleted_count, bytes=report.bytes_freed))
        elif report.kept_count:
            print()
            print(i18n.t("gc.nothing_to_delete", ttl_days=ttl))
    return 0


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # 1) 启动时确定语言
    lang = i18n.detect_lang(args.lang)
    i18n.set_lang(lang)

    # 2) --version 走双语 banner
    if args.version:
        print(i18n.t("cli.banner"))
        print(i18n.t("cli.version", version=VERSION))
        return 0

    # 3) 确保数据目录存在（容错：第一次跑时自动建 ~/.mmi/）
    try:
        paths.ensure_dirs()
    except OSError as e:
        print(i18n.t("cli.init_failed", error=str(e)), file=sys.stderr)
        return 3

    # 4) 启动 banner（仅当用户没显式调用子命令时显示，让 REPL 干净）
    show_banner = args.command not in ("chat",)
    if show_banner:
        print(i18n.t("cli.banner"))
        print(i18n.t("cli.banner.subtitle"))
        print(f"  [lang: {i18n.get_lang()}]")
        print()

    # 5) 子命令分发
    mgr = mgr_module.SessionManager()
    if args.command == "new":
        return cmd_new(args, mgr)
    if args.command == "list":
        return cmd_list(args, mgr)
    if args.command == "stat":
        return cmd_stat(args, mgr)
    if args.command == "export":
        return cmd_export(args, mgr)
    if args.command == "rename":
        return cmd_rename(args, mgr)
    if args.command == "info":
        return cmd_info(args, mgr)
    if args.command == "inspect":
        return cmd_inspect(args, mgr)
    if args.command == "chat":
        return cmd_chat(args, mgr)
    if args.command == "archive":
        return cmd_archive(args, mgr)
    if args.command == "delete":
        return cmd_delete(args, mgr)
    if args.command == "gc":
        return cmd_gc(args, mgr)
    if args.command == "doctor":
        from mmi.tools.doctor import run as run_doctor
        return run_doctor()
    if args.command == "update":
        return cmd_update(args, mgr)
    if args.command == "memory":
        return cmd_memory(args, mgr)
    if args.command == "config":
        return cmd_config(args, mgr)
    if args.command == "agent":
        return cmd_agent(args, mgr)
    if args.command == "skill":
        return cmd_skill(args, mgr)
    if args.command == "tui":
        return cmd_tui(args, mgr)

    # 6) 无子命令：显示帮助
    print(i18n.t("cli.usage") + ":")
    print(f"  mmi {i18n.t('cli.command.new')}")
    print(f"  mmi {i18n.t('cli.command.list')}")
    print(f"  mmi {i18n.t('cli.command.chat')}")
    return 0


    # Round 0.13: auto-inject MMI_HOME for fusion worktree isolation
    import os
    from pathlib import Path
    if "MMI_HOME" not in os.environ:
        os.environ["MMI_HOME"] = str(Path.home() / ".mmi-fusion")

def cmd_update(args, mgr) -> int:
    """增量更新会话热度（不触发 LLM / 不追加正文）。"""
    try:
        mgr.touch(args.session_id)
        print(f"[✓] 会话 {args.session_id} 已更新热度")
    except Exception as e:
        print(f"[✗] 更新失败: {e}")
        return 1
    return 0


def cmd_memory(args, mgr) -> int:
    """跨会话记忆子命令：search / count / clear。"""
    from mmi.core import memory

    sub = getattr(args, "memory_cmd", None)
    if sub is None:
        print("usage: mmi memory {search|count|clear}")
        return 1

    if sub == "count":
        n = memory.memory_count()
        print(f"当前记忆条数: {n}")
        return 0

    if sub == "clear":
        if not args.yes:
            print("[!] 这会清空所有跨会话记忆。继续请加 --yes")
            return 1
        memory.clear_memories()
        print("[✓] 记忆已清空")
        return 0

    if sub == "search":
        query = " ".join(args.query).strip()
        if not query:
            print("usage: mmi memory search <关键词...>")
            return 1
        hits = memory.search_semantic(query, top_k=args.top_k)
        if not hits:
            print(f"未找到与「{query}」相关的记忆。")
            return 0
        print(f"找到 {len(hits)} 条与「{query}」相关的记忆:\n")
        for i, h in enumerate(hits, 1):
            print(f"  [{i}] {h.memory_id}")
            print(f"      标题:   {h.title or '(无)'}")
            if h.conclusion:
                print(f"      结论:   {h.conclusion[:120]}")
            print(f"      来源:   session {h.session_id} (turns={h.turns_at})")
            print(f"      时间:   {h.created_at}")
            print()
        return 0

    print(f"unknown memory subcommand: {sub}")
    return 1


    # Round 0.13: auto-inject MMI_HOME for fusion worktree isolation
    import os
    from pathlib import Path
    if "MMI_HOME" not in os.environ:
        os.environ["MMI_HOME"] = str(Path.home() / ".mmi-fusion")

def cmd_tui(args, mgr) -> int:
    """启动 TUI（TypeScript + Ink 渲染层，Python IPC 提供会话/消息/记忆数据）。

    流程：
      1. 检查 node 是否可用，缺失则报错退出 1。
      2. 检查 tui-ts/dist/mmi-tui.js 是否存在；不存在或显式传 --build 时
         自动跑 `npm install && npm run build` 重新打包。
      3. 通过 portalocker 在 ~/.mmi/run/tui.lock 拿非阻塞排他锁，避免
         多个 TUI 同时跑抢同一 IPC 端口。锁被占则友好提示并退出 1。
      4. 用 subprocess.run 跑打包好的 JS bundle,把当前 Python 解释器
         路径注入到子进程 env["PYTHON"],TUI 端会通过这个变量回拉
         IPC server。
      5. 退出时在 finally 里释放锁。
    """
    import os
    import shutil
    import subprocess

    import portalocker

    # 1) node 检查
    node = shutil.which("node")
    if node is None:
        print("Node.js >= 18 未安装。请到 https://nodejs.org/ 安装。", file=sys.stderr)
        return 1

    # 2) 单实例锁：portalocker 非阻塞(LOCK_NB),抢不到就退出 1
    paths.ensure_dirs()
    lock_path = paths.get_root() / "run" / "tui.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = portalocker.Lock(
        str(lock_path),
        mode="w",
        timeout=0.0,
        flags=portalocker.LOCK_EX | portalocker.LOCK_NB,
    )
    try:
        lock.acquire()
    except portalocker.LockException:
        print("已有另一个 `mmi tui` 在运行（lock: {}）。".format(lock_path), file=sys.stderr)
        return 1

    try:
        # 3) dist 检查 / 按需构建
        dist = REPO_ROOT / "tui-ts" / "dist" / "mmi-tui.js"
        if args.build or not dist.exists():
            tui_ts = REPO_ROOT / "tui-ts"
            print("[tui] 安装依赖并构建 bundle（首次 / --build）...", file=sys.stderr)
            npm = shutil.which("npm")
            if npm is None:
                print("npm 未安装,无法构建。", file=sys.stderr)
                return 1
            r1 = subprocess.run([npm, "install"], cwd=str(tui_ts), check=False)
            if r1.returncode != 0:
                return r1.returncode
            r2 = subprocess.run([npm, "run", "build"], cwd=str(tui_ts), check=False)
            if r2.returncode != 0:
                return r2.returncode

        # 4) 启 bundle
        env = os.environ.copy()
        env.setdefault("PYTHON", sys.executable)
        result = subprocess.run([node, str(dist)], env=env, check=False)
        return result.returncode
    finally:
        # 5) 释放锁
        try:
            lock.release()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Round 0.8 新增命令
# ---------------------------------------------------------------------------

    # Round 0.13: auto-inject MMI_HOME for fusion worktree isolation
    import os
    from pathlib import Path
    if "MMI_HOME" not in os.environ:
        os.environ["MMI_HOME"] = str(Path.home() / ".mmi-fusion")

def cmd_rename(args, mgr) -> int:
    """重命名会话标题。"""
    # Round 0.14: auto-inject MMI_HOME for fusion worktree isolation
    import os
    from pathlib import Path
    if "MMI_HOME" not in os.environ:
        os.environ["MMI_HOME"] = str(Path.home() / ".mmi-fusion")

    try:
        sess = storage.read_session(args.session_id)
    except storage.SessionNotFound:
        print(f"session not found: {args.session_id}", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"{e}", file=sys.stderr)
        return 1

    # Check duplicate title unless --force
    if not args.force:
        # Check duplicate title (scan all active sessions)
        for sid in storage.list_session_ids():
            if sid == args.session_id:
                continue
            try:
                other = storage.read_session(sid)
                if other.meta.title == args.title:
                    print(f"title already in use: '{args.title}' (session: {other.meta.session_id})", file=sys.stderr)
                    print("use --force to override", file=sys.stderr)
                    return 1
            except Exception:
                pass

    old_title = sess.meta.title
    sess.meta.title = args.title
    storage.write_session(sess)
    print(f"renamed: '{old_title}' → '{args.title}'")
    return 0


    # Round 0.13: auto-inject MMI_HOME for fusion worktree isolation
    import os
    from pathlib import Path
    if "MMI_HOME" not in os.environ:
        os.environ["MMI_HOME"] = str(Path.home() / ".mmi-fusion")

def cmd_info(args, mgr) -> int:
    """显示单个会话的完整详情。"""
    try:
        sess = storage.read_session(args.session_id)
    except storage.SessionNotFound:
        print(f"session not found: {args.session_id}", file=sys.stderr)
        return 1
    meta = sess.meta
    turns = storage.count_user_turns(sess.body)
    print(f"  Session ID : {meta.session_id}")
    print(f"  Title      : {meta.title}")
    print(f"  Agent      : {meta.agent_id}")
    print(f"  State      : {meta.state}")
    print(f"  Heat       : {meta.heat:.4f}")
    print(f"  Created    : {meta.created_at}")
    print(f"  Updated    : {meta.updated_at}")
    print(f"  Last Access: {meta.last_access}")
    print(f"  Access Count: {meta.access_count}")
    print(f"  User Turns : {turns}")
    print(f"  Trash      : {'yes' if meta.trashed_at else 'no'}")
    if meta.cold_since:
        print(f"  Cold Since : {meta.cold_since}")
    print(f"  Summary    : {meta.summary or '(none)'}")
    print(f"  Keywords   : {', '.join(meta.keywords) or '(none)'}")
    return 0

def cmd_inspect(args, mgr) -> int:
    """Preview context trim result (no LLM call, diagnostic only)."""
    # Round 0.11: auto-inject MMI_HOME for fusion worktree isolation
    import os
    from pathlib import Path
    if "MMI_HOME" not in os.environ:
        os.environ["MMI_HOME"] = str(Path.home() / ".mmi-fusion")
    from mmi.core import context as _loader

    sid = args.session_id
    try:
        mgr.get(sid)
    except Exception:
        print(f"session not found: {sid}", file=sys.stderr)
        return 1

    user_input = args.text if args.text is not None else ""
    config = _loader.LoaderConfig()
    ctx = _loader.build_context_detailed(sid, user_input, config)

    # Build messages to measure system prompt
    messages = _loader.compose_messages(ctx, user_input, config, language=args.lang or "zh-CN")
    sys_msg = next((m for m in messages if m.get("role") == "system"), {})
    sys_content = sys_msg.get("content", "")

    # Header
    print("=" * 60)
    print(f"mmi inspect  |  session={sid}")
    print("=" * 60)
    print(f"  turn_limit    : {config.recent_turns}")
    print(f"  recent_turns  : {len(ctx.recent_turns)} pairs kept")
    print(f"  hit_paragraphs: {len(ctx.hit_turns)} kept")
    print(f"  token_limit   : {config.max_tokens}")
    print(f"  tokens used   : {ctx.estimated_tokens} ({ctx.estimated_tokens/config.max_tokens*100:.1f}%)")
    print()

    # System prompt
    print("[system prompt]")
    print(f"  {len(sys_content)} chars  |  {_loader.estimate_tokens([sys_msg])} tokens")
    print("  %s" % sys_content[:200])

    # Recent turns (collapsible)
    if ctx.recent_turns:
        print("\n[recent turns]  last %d pairs" % len(ctx.recent_turns))
        for j, turn in enumerate(ctx.recent_turns):
            role = turn.get("role","?")
            cont = turn.get("content","")
            print(f"  #{j+1} [{role}] {len(cont)} chars")
            print(f"    {cont[:150].replace(chr(10),' ')}")

    # Hit paragraphs
    if ctx.hit_turns:
        print("\n[hit paragraphs]  %d" % len(ctx.hit_turns))
        for j, hit in enumerate(ctx.hit_turns):
            sc = hit.get("score","?")
            cont = hit.get("content","")
            print(f"  #{j+1}  score={sc}  {len(cont)} chars")
            print(f"    {cont[:120].replace(chr(10),' ')}")

    # Overflow warning
    if ctx.estimated_tokens > config.max_tokens:
        over = ctx.estimated_tokens - config.max_tokens
        pct = over / config.max_tokens * 100
        print(f"\n[!] WARNING: {over} tokens over limit (+{pct:.1f}% overflow)")
    else:
        headroom = config.max_tokens - ctx.estimated_tokens
        print(f"\n[OK] Within limit (headroom={headroom} tokens)")

    return 0

def cmd_config(args, mgr) -> int:
    """LLM 配置子命令:show / wizard。"""
    from mmi.core import config as cfg_mod

    sub = getattr(args, "config_cmd", None)
    if sub is None:
        print("usage: mmi config {show|wizard}")
        return 1

    if sub == "show":
        llm = cfg_mod.get_llm_config()
        if not any(llm.values()):
            print("未配置 LLM。运行 `mmi config wizard` 走交互式设置。")
            return 0
        print("当前 LLM 配置 (~/.mmi/config.toml):")
        for k in ("provider", "base_url", "api_key", "model"):
            v = llm.get(k, "") or ""
            if k == "api_key" and v:
                v = v[:4] + "***" + v[-2:] if len(v) > 6 else "***"
            print(f"  {k:10s} = {v}")
        return 0

    if sub == "wizard":
        return _config_wizard(args)

    print(f"unknown config subcommand: {sub}")
    return 1


def _prompt_choice(prompt: str, options: list[str], default: int = 0) -> int:
    """让用户从编号列表里选一个。返回 index。空输入走 default。"""
    while True:
        raw = input(prompt).strip()
        if not raw:
            return default
        try:
            idx = int(raw)
            if 0 <= idx < len(options):
                return idx
        except ValueError:
            pass
        print(f"  请输入 0-{len(options)-1} 之间的整数")


def _prompt_text(prompt: str, *, required: bool = True, default: str = "") -> str:
    """让用户输入一段文本。空输入走 default;required 时空也再问。"""
    while True:
        suffix = f" [{default}]" if default else ""
        raw = input(f"{prompt}{suffix}: ").strip()
        if not raw:
            raw = default
        if raw or not required:
            return raw
        print("  不能为空,请重新输入")


def _config_wizard(args) -> int:
    """交互式 LLM 配置向导。"""
    from dataclasses import replace
    from mmi.core import config as cfg_mod
    from mmi.core import providers as prov_mod
    from mmi.core import model_fetcher

    print("=" * 50)
    print("  mmi LLM 配置向导")
    print("=" * 50)

    # 显示当前
    current = cfg_mod.get_llm_config()
    if any(current.values()):
        print(f"\n当前: provider={current.get('provider')!r}, "
              f"model={current.get('model')!r}")
        print("(向导会覆盖现有配置,Ctrl+C 随时退出)\n")

    # 1) 选 provider
    providers = list(prov_mod.list_providers())
    print("\n可用的模型商:")
    for i, p in enumerate(providers):
        marker = f" [{p.notes}]" if p.notes else ""
        print(f"  [{i}] {p.name}  (id={p.id}, 默认 base_url: {p.base_url}){marker}")
    custom_idx = len(providers)
    print(f"  [{custom_idx}] 自定义(手填 base_url)")

    if getattr(args, "provider", None):
        pid = args.provider.strip().lower()
        try:
            provider = prov_mod.get_provider(pid) if pid != "custom" else None
            chosen_idx = custom_idx if pid == "custom" else next(
                i for i, p in enumerate(providers) if p.id == pid
            )
        except ValueError:
            print(f"未知 provider: {pid}")
            return 1
    else:
        chosen_idx = _prompt_choice(
            "\n选哪个? (输入编号) ", [p.id for p in providers] + ["custom"],
        )

    if chosen_idx == custom_idx:
        base_url = _prompt_text("自定义 base_url", default=current.get("base_url", ""))
        style_raw = _prompt_text("API 风格 (openai/anthropic)", default="openai").lower()
        if style_raw not in ("openai", "anthropic"):
            print("  style 必须是 openai 或 anthropic")
            return 1
        provider = prov_mod.make_custom_provider(base_url, preferred_api_style=style_raw)
        api_style = style_raw
    else:
        provider = providers[chosen_idx]
        base_url = provider.base_url
        # 双接口的商(deepseek / minimax)问一句协议
        if provider.anthropic_base_url:
            print(f"\n  {provider.name} 同时支持 Anthropic / OpenAI 两种协议。")
            print(f"  [0] Anthropic (推荐,端点: {provider.anthropic_base_url})")
            print(f"  [1] OpenAI 兼容 (端点: {provider.base_url})")
            style_idx = _prompt_choice("  用哪种? (默认 0) ", ["anthropic", "openai"], default=0)
            api_style = "anthropic" if style_idx == 0 else "openai"
            provider = replace(
                provider,
                preferred_api_style=api_style,
                base_url=(
                    provider.anthropic_base_url if api_style == "anthropic"
                    else provider.base_url
                ),
            )
            # 🐛 修复: replace 后同步局部变量,否则配置写入旧 base_url
            base_url = provider.base_url
        else:
            api_style = provider.preferred_api_style
            print(f"  (单协议: {api_style})")

    # 2) api_key
    if getattr(args, "api_key", None):
        api_key = args.api_key.strip()
    else:
        env_hint = provider.api_key_env or "(无)"
        print(f"\nAPI key 来源提示: 配置在 {provider.api_key_url or '?'}")
        print(f"环境变量兼容名: {env_hint}")
        api_key = _prompt_text("粘贴 api_key", required=True)

    if not api_key:
        print("api_key 为空,取消。")
        return 1

    # 3) 拉模型列表(用户已选 style,不再回退)
    if getattr(args, "no_fetch", False):
        if getattr(args, "model", None):
            model_id = args.model.strip()
        else:
            model_id = _prompt_text("模型 id(手填)", required=True)
    else:
        print(f"\n正在拉取 {provider.name} 的可用模型(走 {api_style} 端点: {provider.base_url})...")
        try:
            models = model_fetcher.fetch_models(
                provider, api_key, style_override=api_style,
            )
        except model_fetcher.ModelFetchError as e:
            print(f"[!] 拉取失败: {e}")
            if not _confirm("是否仍要手填模型 id 继续?", default=False):
                return 1
            models = []

        if not models:
            model_id = _prompt_text("模型 id(手填)", required=True)
        elif getattr(args, "model", None):
            mid = args.model.strip()
            ids = {m.id for m in models}
            if mid not in ids:
                print(f"  警告: {mid} 不在 API 返回列表里,继续保存")
            model_id = mid
        else:
            print(f"\n拉到 {len(models)} 个模型:")
            show_n = min(30, len(models))
            for i, m in enumerate(models[:show_n]):
                print(f"  [{i}] {m.id}")
            if len(models) > show_n:
                print(f"  ... 共 {len(models)} 个,只显示前 {show_n}")
            idx = _prompt_choice(
                f"\n选哪个? (0-{show_n-1}) ", [m.id for m in models[:show_n]],
            )
            model_id = models[idx].id if 0 <= idx < show_n else ""

    if not model_id:
        print("模型 id 为空,取消。")
        return 1

    # 4) 写盘
    ok = cfg_mod.set_llm_config(
        provider=provider.id,
        base_url=base_url,
        api_key=api_key,
        model=model_id,
        api_style=api_style,
    )
    if not ok:
        print("[!] 写盘失败(权限/磁盘?)")
        return 1
    print("\n[✓] 已写入 ~/.mmi/config.toml:")
    print(f"    provider  = {provider.id}")
    print(f"    api_style = {api_style}")
    print(f"    base_url  = {base_url}")
    print(f"    api_key   = {api_key[:4]}***{api_key[-2:]}" if len(api_key) > 6 else "    api_key   = ***")
    print(f"    model     = {model_id}")
    return 0


def _confirm(prompt: str, *, default: bool = False) -> bool:
    """Yes/No 确认。"""
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        raw = input(f"{prompt} {suffix}: ").strip().lower()
        if not raw:
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False


def cmd_agent(args, mgr) -> int:
    """3.9 mmi agent list/invoke."""
    from mmi.agent.registry import AgentRegistry
    from mmi.agent.builtin import CodeReviewAgent, DocAgent  # noqa: F401

    sub = getattr(args, "agent_cmd", None)
    if sub is None:
        print("usage: mmi agent {list|invoke}")
        return 1

    # 注册内置 Agent(幂等)
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
        from mmi.agent.orchestrator import Orchestrator
        from mmi.agent.modes import ThinkingMode as TM

        agent_id = args.agent_id
        agent_cls = reg.match(agent_id)
        if agent_cls is None:
            print(f"[!] Agent {agent_id!r} 未注册")
            return 1
        # 构造 orchestrator
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


def _register_builtin_agents(reg) -> None:
    """3.9:把内置 Agent 注册到 registry(幂等,重复注册 ValueError 被吞)。"""
    from mmi.agent.builtin import CodeReviewAgent, DocAgent
    from mmi.agent.registry import AgentMeta
    try:
        reg.register(AgentMeta(
            agent_id="code_review",
            name="Code Review",
            description="审查/重构/审计源码",
            tags=["code", "review", "security", "audit"],
            version="0.1.0",
            builtin=True,
        ), CodeReviewAgent)
    except ValueError:
        pass
    try:
        reg.register(AgentMeta(
            agent_id="doc",
            name="Doc",
            description="生成文档/翻译",
            tags=["doc", "docstring", "translation"],
            version="0.1.0",
            builtin=True,
        ), DocAgent)
    except ValueError:
        pass


def cmd_skill(args, mgr) -> int:
    """3.12 mmi skill list/search/create."""
    from mmi.agent.skill import Skill, SkillLibrary, SkillType
    from datetime import datetime, timezone

    sub = getattr(args, "skill_cmd", None)
    if sub is None:
        print("usage: mmi skill {list|search|create}")
        return 1

    lib = SkillLibrary.get_instance()

    if sub == "list":
        skills = list(lib._skills.values()) if hasattr(lib, "_skills") else []
        if not skills:
            print("无 Skill。试用 `mmi skill create` 添加。")
            return 0
        print(f"共 {len(skills)} 个 Skill:\n")
        for s in skills:
            print(f"  [{s.skill_id:20s}] {s.name}  ({s.skill_type.name})")
            print(f"      {s.apply_scene}")
        return 0

    if sub == "search":
        query = args.query
        matches = lib.match(query, limit=10)
        if not matches:
            print(f"未找到匹配 {query!r} 的 Skill")
            return 0
        print(f"找到 {len(matches)} 个匹配:\n")
        for s in matches:
            print(f"  [{s.skill_id:20s}] {s.name}  ({s.skill_type.name})")
            print(f"      {s.apply_scene[:60]}")
        return 0

    if sub == "create":
        now = datetime.now(timezone.utc).isoformat()
        tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]
        skill = Skill(
            skill_id=args.skill_id,
            name=args.name,
            skill_type=SkillType.BUILTIN,  # 用户创建标 BUILTIN,后续 6.1 区分
            content=args.content,
            apply_scene=args.apply_scene,
            tags=tags,
            created_at=now,
            updated_at=now,
        )
        try:
            lib.create(skill)
            print(f"[✓] Skill {args.skill_id!r} 已创建")
            return 0
        except ValueError as e:
            print(f"[!] {e}")
            return 1

    print(f"unknown skill subcommand: {sub}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
