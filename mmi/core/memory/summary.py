"""mmi.core.memory.summary —— 从对话 body 抽结构化摘要。

两种模式:
  - LLM 模式(传 llm):让 LLM 抽 {主题, 决策, 关键结论, 待办} 四个字段
  - 规则模式(默认,不传 llm):从 markdown 头/尾提 title + conclusion

LLM 模式失败时自动降级到规则模式,不抛错(摘要是辅助,坏了别影响主流程)。

依赖项:无（除 json/re stdlib）。
被依赖:store。
"""

from __future__ import annotations

import json
import re
from typing import Any

_STRUCTURED_PROMPT_ZH = (
    "请从以下对话中提取结构化摘要,严格用 JSON 格式输出,字段固定为:\n"
    '  {"title": "...", "decision": "...", "conclusion": "...", "todos": "..."}\n'
    "- title: 一句话主题(<= 30 字)\n"
    "- decision: 做出的关键决策(无则空字符串)\n"
    "- conclusion: 关键结论(无则空字符串)\n"
    "- todos: 待办事项,多条用「;」分隔(无则空字符串)\n"
    "只输出 JSON,不要任何前后缀。"
)
_STRUCTURED_PROMPT_EN = (
    "Extract a structured summary from the conversation below. "
    'Output STRICT JSON with exactly these fields:\n'
    '  {"title": "...", "decision": "...", "conclusion": "...", "todos": "..."}\n'
    "- title: one-line topic (<= 30 chars)\n"
    "- decision: key decision made (empty if none)\n"
    "- conclusion: key conclusion (empty if none)\n"
    "- todos: pending items, ';' separated (empty if none)\n"
    "Output JSON only, no prefix or explanation."
)


def _build_structured_summary_rules(body: str) -> dict[str, str]:
    """规则版:从 markdown 头/尾提 title + conclusion。"""
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    title = ""
    for ln in lines:
        if ln.startswith("#"):
            title = ln.lstrip("#").strip()
            break
    if not title and lines:
        title = lines[0][:80]
    conclusion = lines[-1][:200] if lines else ""
    return {"title": title, "decision": "", "conclusion": conclusion, "todos": ""}


def _build_structured_summary_llm(
    body: str, *, language: str, llm: Any,
) -> dict[str, str]:
    """LLM 抽 {主题, 决策, 结论, 待办}。失败由调用方降级。"""
    prompt = _STRUCTURED_PROMPT_ZH if language.startswith("zh") else _STRUCTURED_PROMPT_EN
    # 截断 body 避免 prompt 过长(8k 字符够用)
    body_truncated = body[:8000]
    user_msg = (
        f"{prompt}\n\n对话全文:\n{body_truncated}"
        if language.startswith("zh")
        else f"{prompt}\n\nConversation:\n{body_truncated}"
    )
    raw = llm.chat(
        [
            {"role": "user", "content": user_msg},
        ],
        max_tokens=300,
        temperature=0.0,
    )
    return _parse_structured_json(raw, body_for_fallback=body)


def _parse_structured_json(
    raw: str, *, body_for_fallback: str,
) -> dict[str, str]:
    """从 LLM 输出里抠 JSON。解析失败 → 用原 body 走规则版(不污染)。"""
    text = (raw or "").strip()
    # 去掉 markdown 代码块围栏
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    # 找第一个 { 到最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0 or end <= start:
        return _build_structured_summary_rules(body_for_fallback)
    try:
        obj = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return _build_structured_summary_rules(body_for_fallback)
    if not isinstance(obj, dict):
        return _build_structured_summary_rules(body_for_fallback)
    return {
        "title": str(obj.get("title", "") or "").strip()[:200],
        "decision": str(obj.get("decision", "") or "").strip()[:500],
        "conclusion": str(obj.get("conclusion", "") or "").strip()[:500],
        "todos": str(obj.get("todos", "") or "").strip()[:500],
    }


def build_structured_summary(
    body: str,
    *,
    language: str = "zh-CN",
    llm: Any = None,
) -> dict[str, str]:
    """从对话正文提取结构化摘要。

    两种模式:
      - LLM 模式(传 llm):让 LLM 抽 {主题, 决策, 关键结论, 待办} 四个字段
      - 规则模式(默认,不传 llm):从 markdown 头/尾提 title + conclusion

    LLM 模式失败时自动降级到规则模式,不抛错(摘要是辅助,坏了别影响主流程)。

    Args:
        body: Markdown body
        language: 输出语言(影响 prompt)
        llm: LLMProvider(要有 chat 方法)

    Returns:
        dict with keys: title, decision, conclusion, todos(都是 str)
    """
    if not body or not body.strip():
        return {"title": "", "decision": "", "conclusion": "", "todos": ""}
    if llm is not None:
        try:
            return _build_structured_summary_llm(body, language=language, llm=llm)
        except Exception:
            # 降级到规则版
            pass
    return _build_structured_summary_rules(body)
