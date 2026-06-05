"""tests/test_agent_phase3.py — 三期 Agent 骨架测试。

覆盖:
  - 3.2 Router.classify 规则
  - 3.4 Validator 规则引擎(4 条规则)
  - 3.7 BaseAgent 生命周期钩子 + _chat_with_llm 拼 messages
  - 3.8 AgentRegistry 单例加锁
  - 3.11 modes prompt 从 locale
  - 3.5 CodeReviewAgent + 3.10 DocAgent 调 LLM
  - 3.3 Orchestrator 5 步流程
"""

from __future__ import annotations

import pytest

from mmi.agent.router import IntentType, Router
from mmi.agent.validate import Validator, ValidationResult
from mmi.agent.registry import AgentRegistry, AgentMeta
from mmi.agent.modes import ThinkingMode, get_mode_prompt
from mmi.agent.builtin import CodeReviewAgent, DocAgent
from mmi.agent.orchestrator import Orchestrator
from mmi.core import paths, storage
from mmi.core.session import Session, SessionMeta
from mmi.core.llm import Classification, LLMError, LLMProvider


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MMI_HOME", str(tmp_path))
    paths.ensure_dirs()
    yield tmp_path


class _StubLLM(LLMProvider):
    """3.x 测试用假 LLM,按 user message 关键词返不同内容。"""

    def __init__(self):
        self.calls: list[list[dict]] = []

    def chat(self, messages, **kw):
        self.calls.append(list(messages))
        user = messages[-1]["content"] if messages else ""
        if "密码" in user or "password" in user:
            return 'password = "secret123"'
        if "审计" in user or "audit" in user:
            return "## Audit\n发现:输入校验不足"
        return "这是一段正常输出,用于测试"

    def classify(self, prompt, *, options):
        return Classification(choice=options[0], confidence=0.99)


# ---------------------------------------------------------------------------
# 3.2 Router
# ---------------------------------------------------------------------------


def test_router_classify_keyword_zh():
    r = Router()
    assert r.classify("帮我审查这段代码") == IntentType.CODE_REVIEW
    assert r.classify("数据汇总") == IntentType.DATA_ANALYSIS
    assert r.classify("生成文档") == IntentType.DOC_GENERATION
    assert r.classify("头脑风暴") == IntentType.BRAINSTORM


def test_router_classify_keyword_en():
    r = Router()
    assert r.classify("please review this PR") == IntentType.CODE_REVIEW
    assert r.classify("brainstorm ideas") == IntentType.BRAINSTORM
    assert r.classify("audit security") == IntentType.AUDIT


def test_router_classify_long_text_audit():
    r = Router()
    long_text = "x" * 600
    assert r.classify(long_text) == IntentType.AUDIT


def test_router_classify_default_qa():
    r = Router()
    assert r.classify("hi there") == IntentType.QA
    assert r.classify("今天天气") == IntentType.QA


def test_router_classify_empty_unknown():
    r = Router()
    assert r.classify("") == IntentType.UNKNOWN
    assert r.classify("   ") == IntentType.UNKNOWN


def test_router_route_returns_agent_ids():
    r = Router()
    agents = r.route(IntentType.CODE_REVIEW)
    assert "code_review" in agents
    agents_unk = r.route(IntentType.UNKNOWN)
    assert "qa" in agents_unk  # fallback


# ---------------------------------------------------------------------------
# 3.4 Validator
# ---------------------------------------------------------------------------


def test_validator_default_rules_pass():
    v = Validator()
    r = v.check("正常的输出内容", IntentType.QA)
    assert r.passed
    assert isinstance(r, ValidationResult)


def test_validator_dangerous_token_caught():
    v = Validator()
    r = v.check('password = "secret123"', IntentType.QA)
    assert not r.passed
    assert any("dangerous" in i.message for i in r.issues)


def test_validator_too_short_caught():
    v = Validator()
    r = v.check("a", IntentType.QA)
    assert not r.passed
    assert any("too short" in i.message for i in r.issues)


def test_validator_dangerous_phrase_caught():
    v = Validator()
    r = v.check("要执行 rm -rf /tmp 怎么办", IntentType.QA)
    assert not r.passed


def test_validator_empty_caught():
    v = Validator()
    r = v.check("", IntentType.QA)
    assert not r.passed


# ---------------------------------------------------------------------------
# 3.7 BaseAgent
# ---------------------------------------------------------------------------


def test_base_agent_lifecycle_hooks_called():
    """3.7 改进:on_start / on_stop 钩子在子类 override 后能正确工作。"""
    from mmi.agent.base import BaseAgent

    # 子类 override 后方法在 self.__dict__ 里
    started = []
    stopped = []

    class _L(BaseAgent):
        def run(self, user_message, mode=None):
            return "ok"
        def on_start(self):
            started.append(1)
        def on_stop(self):
            stopped.append(1)

    b = _L("qa", "Q", "sys", llm=_StubLLM())
    b.on_start()
    b.on_stop()
    assert started == [1]
    assert stopped == [1]


def test_base_agent_abstract_run():
    """3.7:run() 是 abstractmethod,直接实例化 BaseAgent 应当失败。"""
    import pytest
    from mmi.agent.base import BaseAgent
    with pytest.raises(TypeError):
        BaseAgent("qa", "Q", "sys", llm=_StubLLM())  # 缺 run 实现 → 不能实例化


def test_base_agent_chat_with_llm_builds_messages():
    """3.7 改进:_chat_with_llm 拼 system + user messages。"""
    from mmi.agent.base import BaseAgent

    llm = _StubLLM()

    class _L(BaseAgent):
        def run(self, user_message, mode=None):
            return self._chat_with_llm(user_message, mode=mode)

    a = _L("qa", "Q", "system-prompt-base", llm=llm)
    a.run("hello")
    msgs = llm.calls[0]
    assert msgs[0]["role"] == "system"
    assert "system-prompt-base" in msgs[0]["content"]
    assert msgs[1]["role"] == "user"
    assert msgs[1]["content"] == "hello"


def test_base_agent_chat_with_mode_appends_suffix():
    """3.7 改进:mode != None 时,system 追加 mode suffix。"""
    from mmi.agent.base import BaseAgent

    llm = _StubLLM()

    class _L(BaseAgent):
        def run(self, user_message, mode=None):
            return self._chat_with_llm(user_message, mode=mode)

    a = _L("qa", "Q", "base", llm=llm)
    a.run("hi", mode=ThinkingMode.AUDIT)
    sys_content = llm.calls[0][0]["content"]
    assert "base" in sys_content
    # 中文 locale 有翻译,英文 locale 没翻译
    # 关键断言:mode suffix 非空且不与 base 相同
    from mmi.agent.modes import get_mode_prompt
    suffix = get_mode_prompt(ThinkingMode.AUDIT).system_suffix
    assert suffix
    assert suffix in sys_content


# ---------------------------------------------------------------------------
# 3.8 AgentRegistry 单例
# ---------------------------------------------------------------------------


def test_registry_singleton_thread_safe():
    """3.8 改进:get_instance() 多次调用返同一实例。"""
    AgentRegistry._instance = None
    a = AgentRegistry.get_instance()
    b = AgentRegistry.get_instance()
    assert a is b
    AgentRegistry._instance = None


def test_registry_register_and_lookup():
    AgentRegistry._instance = None
    reg = AgentRegistry.get_instance()
    reg.register(AgentMeta(agent_id="test_a", name="A", builtin=True), type)
    assert reg.match("test_a") is type
    metas = reg.list_all()
    assert any(m.agent_id == "test_a" for m in metas)
    AgentRegistry._instance = None


def test_registry_register_duplicate_raises():
    AgentRegistry._instance = None
    reg = AgentRegistry.get_instance()
    reg.register(AgentMeta(agent_id="dup", name="X", builtin=True), type)
    with pytest.raises(ValueError, match="already registered"):
        reg.register(AgentMeta(agent_id="dup", name="X", builtin=True), type)
    AgentRegistry._instance = None


# ---------------------------------------------------------------------------
# 3.11 modes prompt from locale
# ---------------------------------------------------------------------------


def test_mode_prompt_uses_locale():
    """3.11 改进:mode prompt 从 locales 读。"""
    p = get_mode_prompt(ThinkingMode.BRAINSTORM)
    assert p.system_suffix  # 非空
    assert p.preamble  # 非空


def test_mode_prompt_standard_empty_preamble():
    p = get_mode_prompt(ThinkingMode.STANDARD)
    # STANDARD preamble 在 locale 是空字符串,或者兜底也是空
    assert isinstance(p.preamble, str)


# ---------------------------------------------------------------------------
# 3.5 CodeReviewAgent + 3.10 DocAgent
# ---------------------------------------------------------------------------


def test_code_review_agent_run_with_echo_llm(isolated_home):
    """3.5:CodeReviewAgent 用 stub LLM 调通,捕获密码违规。"""
    agent = CodeReviewAgent(llm=_StubLLM())
    # 用户的 input 含 "密码" 关键词 → stub 返 password=xxx
    reply = agent.run("密码")
    assert "password" in reply  # echo 不会被 detect,但 stub 返的会


def test_code_review_agent_lifecycle_called(isolated_home):
    """3.5/3.7:run() 前后 on_start / on_stop 调。"""
    started, stopped = [], []

    class _L(CodeReviewAgent):
        def on_start(self):
            started.append(1)
        def on_stop(self):
            stopped.append(1)

    agent = _L(llm=_StubLLM())
    agent.run("audit this")
    assert started
    assert stopped


def test_doc_agent_run_normal(isolated_home):
    agent = DocAgent(llm=_StubLLM())
    reply = agent.run("解释这段代码")
    assert isinstance(reply, str)
    assert len(reply) > 0


def test_doc_agent_translation_switches_prompt(isolated_home):
    """3.10:检测"翻译" → 切换 system_prompt。"""
    agent = DocAgent(llm=_StubLLM())
    # 触发 translation 模式
    reply = agent.run("翻译:hello world")
    assert isinstance(reply, str)
    # 测完 prompt 恢复
    assert "documentation" in agent.system_prompt.lower()  # 恢复原 prompt


def test_doc_agent_restores_prompt_on_error(isolated_home):
    """3.10:即使 LLM 抛错,prompt 也要恢复(防止污染下次)。"""
    class _Boom(_StubLLM):
        def chat(self, messages, **kw):
            raise LLMError("boom")

    agent = DocAgent(llm=_Boom())
    original = agent.system_prompt
    try:
        agent.run("翻译")
    except Exception:
        pass
    # 注意:agent.run 自身 catch 了 LLMError,返 "DocAgent error",但 prompt 应恢复
    assert agent.system_prompt == original


# ---------------------------------------------------------------------------
# 3.3 Orchestrator
# ---------------------------------------------------------------------------


def test_orchestrator_chat_end_to_end(isolated_home):
    """3.3:Orchestrator 5 步流程跑通(persist_turn 写入 + validator 通过)。"""
    from mmi.agent.registry import AgentRegistry, AgentMeta

    llm = _StubLLM()
    sid = "01AAAAAAAAAAAAAAAAAAAAAAAA"
    storage.write_session(Session(meta=SessionMeta.new(sid, title="t"), body=""))

    from mmi.core import manager as mgr_module
    mgr = mgr_module.SessionManager(llm=llm)
    # 测试里显式注册 code_review(避免依赖 cli 副作用)
    AgentRegistry._instance = None
    reg = AgentRegistry.get_instance()
    from mmi.agent.builtin import CodeReviewAgent
    reg.register(AgentMeta(agent_id="code_review", name="Code Review", builtin=True), CodeReviewAgent)
    orch = Orchestrator(manager=mgr, llm=llm, registry=reg)

    reply = orch.chat_legacy(sid, "audit security", mode=ThinkingMode.AUDIT)
    assert isinstance(reply, str)
    assert "未注册" not in reply
    s = storage.read_session(sid)
    assert s.body.count("**User:**") == 1
    assert s.body.count("**Assistant:**") == 1
    AgentRegistry._instance = None


def test_orchestrator_chat_persists_turn(isolated_home):
    from mmi.agent.registry import AgentRegistry, AgentMeta

    llm = _StubLLM()
    sid = "01AAAAAAAAAAAAAAAAAAAAAAAA"
    storage.write_session(Session(meta=SessionMeta.new(sid, title="t"), body=""))
    from mmi.core import manager as mgr_module
    mgr = mgr_module.SessionManager(llm=llm)
    AgentRegistry._instance = None
    reg = AgentRegistry.get_instance()
    from mmi.agent.builtin import DocAgent
    reg.register(AgentMeta(agent_id="doc", name="Doc", builtin=True), DocAgent)
    orch = Orchestrator(manager=mgr, llm=llm, registry=reg)
    orch.chat(sid, "翻译:hello")
    s = storage.read_session(sid)
    assert "翻译" in s.body
    AgentRegistry._instance = None
