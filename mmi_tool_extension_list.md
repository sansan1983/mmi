# MMI 工具扩展清单（按优先级排序）

> 生成时间：2026-06-13 | 基于代码调研 + MMI_PHASE_PLAN.md + global_mem.txt

---

## 当前 MMI 工具现状

| 项目 | 内容 |
|------|------|
| 已注册 @tool | 仅 `search`（网页搜索）1 个 |
| 内置子 Agent | CodeReviewAgent（代码审查）、DocAgent（文档/翻译） |
| 工具框架 | @tool 装饰器 + ToolRegistry + discover_builtin_tools() — 就绪 |
| 自动发现路径 | `mmi/agent/builtin/` 下的模块会被自动扫描注册 |

---

## 🔴 P0：核心能力补全（最优先，当前缺失严重影响可用性）

| 优先级 | 工具/能力 | 说明 | 参考来源 |
|--------|----------|------|---------|
| **P0-1** | **文件系统工具（File I/O）** | 读写文件、遍历目录、搜索文件内容、patch 文件 — Agent 无法操作文件 | `GenericAgent` 的 `file_read`/`file_write`/`file_patch` |
| **P0-2** | **代码执行工具（Code Exec）** | 执行 Python/Bash 脚本，捕获 stdout/stderr/exit_code — Agent 无法自主验证 | `GenericAgent` 的 `code_run` |
| **P0-3** | **网页浏览工具（Web Browse）** | 获取网页 HTML/纯文本、执行 JS、切换标签页 — 当前只有搜索没有浏览 | `GenericAgent` 的 `web_scan`/`web_execute_js` |
| **P0-4** | **图片理解/生成（Image）** | 图片 OCR、描述分析、图像生成 — 补齐多模态短板 | `vision_sop`、`agnes_image`、`ocr_utils` |
| **P0-5** | **记忆读写工具（Memory）** | mmi 自有 FAISS+语义记忆引擎，但 Agent 层缺少接口直接读写记忆 | `mmi/core/memory/` 已有引擎未暴露为工具 |

---

## 🟡 P1：消息平台接入（用户明确需求）

| 优先级 | 消息平台 | 说明 | 实现路径 |
|--------|---------|------|---------|
| **P1-1** | **飞书（Feishu）** | **最高优先级** — 已有完整 SOP 和 relay 网关代码，直接封装为 @tool | `sop_feishu_send_image`、`sop_feishu_send_file`、`/home/ubuntu/nexus-gateway/relay.py` |
| **P1-2** | **微信（WeChat）** | 用户常用平台，偏好 16px/2.0 行距，已有部分工具链 | 封装现有微信接口为统一 @tool |
| **P1-3** | **Telegram** | 通用 Bot API，接入简单 | 全新开发 |
| **P1-4** | **飞书流式卡片增强** | 支持流式输出+富文本卡片排版 | `relay_sop.md` 已有 FeishuCardStream 设计 |

---

## 🟡 P2：GA 已有工具移植（快速见效）

| 优先级 | 工具 | 说明 | 来源 |
|------|------|------|------|
| **P2-1** | **search 增强** | 多源搜索 + Token Plan 额度管理（60次/5h） | `global_mem.txt` 网络搜索策略 |
| **P2-2** | **代理管理（Proxy）** | mihomo 代理开关、状态检查 | `mihomo_proxy_sop` |
| **P2-3** | **进程监控（Process）** | 查看/重启 watchdog、relay、scheduler 等后台进程 | 用户指令别名 + `tmux` |
| **P2-4** | **ADB/UI 检测** | 手机/界面自动化操作 | `adb_ui`、`ui_detect` |
| **P2-5** | **定时任务（Scheduler）** | 查看/管理定时后台任务 | `scheduler.py` + `sche_checkpoint` |
| **P2-6** | **视频生成（Video）** | 文本到视频生成 | `agnes_video` |

---

## 🟢 P3：架构完善工具（MMI_PHASE_PLAN 六期规划）

| 优先级 | 工具/能力 | 说明 | 规划阶段 |
|------|----------|------|---------|
| **P3-1** | **Skill 持久化** | Skill 当前存内存，重启丢失 | 六期 6.1 |
| **P3-2** | **Trace 持久化** | trace 数据无持久化，无法审计 | 六期 6.3 |
| **P3-3** | **Provider 健康检测** | LLM Provider 故障时自动切换/降级 | 六期 6.5 |
| **P3-4** | **Config Schema 校验** | 防止手动编辑 config.toml 写入非法值 | P1A-4 |
| **P3-5** | **GC 存储工具** | 记忆垃圾回收状态查询与手动触发 | P1A-1 |
| **P3-6** | **API Key 安全存储** | 加密存储密钥，不暴露明文 | P1A-3 |

---

## 🔵 P4：生态扩展工具（长期目标）

| 优先级 | 工具/能力 | 说明 |
|------|----------|------|
| **P4-1** | **MCP 协议工具** | Model Context Protocol 集成，连接外部工具生态 |
| **P4-2** | **LLM Deep Audit** | 高风险输出二次审查（六期 6.9） |
| **P4-3** | **Web GUI 工具** | Web 管理界面（六期 6.10） |
| **P4-4** | **GitHub 集成工具** | PR 管理、Release 发布、代码审查联动 |
| **P4-5** | **项目管理工具** | Goal/Checklist/Review 流水线 |

---

## 📊 汇总

```
当前:  1 个 @tool(search) + 2 个子 Agent
目标:  P0(5) + P1(4) + P2(6) + P3(6) + P4(5) = 26 项扩展
```

### 实施建议

1. **P0 先行** — 文件系统 + 代码执行 + 网页浏览是 Agent 自主工作的基石
2. **消息平台紧跟** — 飞书已有 relay 代码和 SOP，改造成 @tool 成本最低
3. **复用 GA 生态** — P2 的 6 项在 GenericAgent 中已有成熟实现，直接参考移植
4. **架构已就绪** — @tool 装饰器 + discover_builtin_tools() 自动发现机制已可用，新工具放在 `mmi/agent/builtin/` 下即可自动注册

---

*本文件由 GenericAgent 自动生成*
