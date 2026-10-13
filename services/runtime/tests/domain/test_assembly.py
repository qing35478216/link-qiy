"""上下文装配纯函数用例（工单验收标准 1：给定输入集合输出确定 prompt）。

覆盖：
- 确定性（同输入两次装配 → 完全相同）
- 四段装配结构（system / knowledge / history / question 顺序与内容）
- 变量渲染（已知替换、未知保留）
- token 预算（历史轮次从新到旧贪心、装不下的轮即停）
- 预算溢出（系统/问题本身超长 → ContextOverflowError）
- 直通模式（无 appCode：messages 原样）
- 知识库命中（贪心装入 + 跳过装不下的单条）
"""

from __future__ import annotations

import pytest

from linkai_runtime.domain.app_profile import AppProfile
from linkai_runtime.domain.assembly import (
    DEFAULT_MEMORY_ROUNDS,
    AssemblyInput,
    KnowledgeHit,
    assemble_context,
    render_variables,
)
from linkai_runtime.domain.chat import ChatMessage, MessageRole
from linkai_runtime.domain.errors import ContextOverflowError

TS = "2026-10-13T00:00:00+00:00"


def _msg(role: MessageRole, content: str) -> ChatMessage:
    return ChatMessage(role=role, content=content)


def _history(*pairs: tuple[str, str]) -> tuple[ChatMessage, ...]:
    out: list[ChatMessage] = []
    for user, assistant in pairs:
        out.append(_msg(MessageRole.USER, user))
        out.append(_msg(MessageRole.ASSISTANT, assistant))
    return tuple(out)


def _profile(**overrides: object) -> AppProfile:
    from linkai_runtime.domain.app_profile import PromptVariable

    base: dict[str, object] = {
        "app_code": "demo",
        "app_name": "演示",
        "system_prompt": "你是客服助手。",
        "model_code": "deepseek-chat",
        "temperature": 0.7,
        "memory_rounds": 3,
        "context_length": 4096,
        "max_tokens": 512,
        "variables": (PromptVariable(name="role", value="客服"),),
    }
    base.update(overrides)
    return AppProfile(**base)  # type: ignore[arg-type]


def _input(profile: AppProfile | None, **overrides: object) -> AssemblyInput:
    base: dict[str, object] = {
        "profile": profile,
        "history": (),
        "knowledge_hits": (),
        "question": "今天天气怎么样？",
        "variables": {},
    }
    base.update(overrides)
    return AssemblyInput(**base)  # type: ignore[arg-type]


class TestDeterminism:
    """验收标准 1：输入集合确定 → 输出确定。"""

    def test_same_input_same_output(self) -> None:
        profile = _profile()
        history = _history(("第一问", "第一答"), ("第二问", "第二答"))
        inp = _input(profile, history=history, variables={"role": "客服"})
        first = assemble_context(inp)
        second = assemble_context(inp)
        assert [m.to_dict() for m in first.messages] == [m.to_dict() for m in second.messages]
        assert first.tokens == second.tokens
        assert first.prompt_budget == second.prompt_budget
        assert first.dropped_history_turns == second.dropped_history_turns

    def test_output_is_json_serializable(self) -> None:
        import json

        result = assemble_context(_input(_profile(), history=_history(("问", "答"))))
        payload = json.dumps([m.to_dict() for m in result.messages], ensure_ascii=False)
        assert "你是客服助手。" in payload


class TestAppModeStructure:
    """四段装配的结构与顺序。"""

    def test_four_sections_in_order(self) -> None:
        profile = _profile()
        history = _history(("之前的问题", "之前的回答"))
        hits = (KnowledgeHit(hit_id="d1", content="知识内容甲", score=0.9),)
        result = assemble_context(
            _input(profile, history=history, knowledge_hits=hits, question="本次提问")
        )
        roles = [m.role for m in result.messages]
        assert roles == [
            MessageRole.SYSTEM,  # 应用设定
            MessageRole.SYSTEM,  # 知识库命中
            MessageRole.USER,  # 历史 user
            MessageRole.ASSISTANT,  # 历史 assistant
            MessageRole.USER,  # 本次问答
        ]
        assert result.messages[0].content == "你是客服助手。"
        assert "知识内容甲" in result.messages[1].content
        assert result.messages[-1].content == "本次提问"

    def test_no_system_prompt_no_system_message(self) -> None:
        profile = _profile(system_prompt=None)
        result = assemble_context(_input(profile))
        assert all(m.role is not MessageRole.SYSTEM for m in result.messages)
        assert result.messages[-1].content == "今天天气怎么样？"

    def test_memory_rounds_trims_history(self) -> None:
        profile = _profile(memory_rounds=2)
        history = _history(
            ("轮1问", "轮1答"), ("轮2问", "轮2答"), ("轮3问", "轮3答"), ("轮4问", "轮4答")
        )
        result = assemble_context(_input(profile, history=history))
        # 只保留最新 2 轮（轮3、轮4）
        contents = [m.content for m in result.messages]
        assert "轮1问" not in contents and "轮2问" not in contents
        assert "轮3问" in contents and "轮4问" in contents
        assert result.dropped_history_turns == 2

    def test_odd_history_trailing_user_is_own_turn(self) -> None:
        profile = _profile(memory_rounds=5)
        history = (
            _msg(MessageRole.USER, "问1"),
            _msg(MessageRole.ASSISTANT, "答1"),
            _msg(MessageRole.USER, "问2（无答复）"),
        )
        result = assemble_context(_input(profile, history=history))
        contents = [m.content for m in result.messages]
        assert contents == ["你是客服助手。", "问1", "答1", "问2（无答复）", "今天天气怎么样？"]


class TestVariables:
    """变量渲染。"""

    def test_known_variables_rendered(self) -> None:
        profile = _profile(system_prompt="你是{{role}}，公司是{{company}}。")
        result = assemble_context(_input(profile, variables={"role": "售后", "company": "LinkAI"}))
        assert result.messages[0].content == "你是售后，公司是LinkAI。"

    def test_request_variables_override_profile_defaults(self) -> None:
        profile = _profile(system_prompt="你是{{role}}。")
        result = assemble_context(_input(profile, variables={"role": "售前"}))
        assert result.messages[0].content == "你是售前。"

    def test_unknown_placeholder_kept_literal(self) -> None:
        profile = _profile(system_prompt="你好{{name}}，{{unknown}}")
        result = assemble_context(_input(profile, variables={"name": "世界"}))
        assert result.messages[0].content == "你好世界，{{unknown}}"

    def test_render_variables_accepts_inner_spaces(self) -> None:
        assert render_variables("a{{  x  }}b", {"x": "1"}) == "a1b"


class TestBudget:
    """token 预算：历史轮次贪心 + 溢出即错。"""

    def test_history_fills_until_budget_then_stops(self) -> None:
        # prompt 预算 = 200 - 100 = 100；系统(2)+问题(8) 后剩 90。
        # 旧轮（120 token/轮）装不下 → 停；新轮（12 token/轮）装入。
        profile = _profile(
            system_prompt="简。", context_length=200, max_tokens=100, memory_rounds=5
        )
        history = _history(
            ("旧问" * 30, "旧答" * 30),  # 巨大，装不下
            ("新问", "新答"),  # 小，装得下
        )
        result = assemble_context(_input(profile, history=history))
        contents = [m.content for m in result.messages]
        assert "新问" in contents and "新答" in contents
        assert "旧问" * 30 not in contents
        assert result.dropped_history_turns == 1

    def test_overflow_when_system_plus_question_exceeds_budget(self) -> None:
        profile = _profile(system_prompt="系统" * 50, context_length=60, max_tokens=50)
        with pytest.raises(ContextOverflowError) as exc_info:
            assemble_context(_input(profile, question="问题" * 50))
        assert exc_info.value.code == "CONTEXT_OVERFLOW"

    def test_overflow_when_budget_non_positive(self) -> None:
        profile = _profile(context_length=100, max_tokens=200)
        with pytest.raises(ContextOverflowError):
            assemble_context(_input(profile))

    def test_max_tokens_override_shrinks_prompt_budget(self) -> None:
        profile = _profile(context_length=200, max_tokens=100)
        result_default = assemble_context(_input(profile))
        result_override = assemble_context(_input(profile, max_tokens_override=150))
        assert result_override.prompt_budget == 50
        assert result_default.prompt_budget == 100


class TestKnowledge:
    """知识库命中：贪心 + 跳过。"""

    def test_hits_included_in_order_with_ids(self) -> None:
        profile = _profile()
        hits = (
            KnowledgeHit(hit_id="d1", content="内容一", score=0.9),
            KnowledgeHit(hit_id="d2", content="内容二", score=0.8),
        )
        result = assemble_context(_input(profile, knowledge_hits=hits))
        assert result.knowledge_included == ("d1", "d2")
        assert result.knowledge_dropped == 0
        knowledge_msg = result.messages[1]
        assert "内容一" in knowledge_msg.content and "内容二" in knowledge_msg.content

    def test_oversized_hit_skipped_smaller_later_hit_included(self) -> None:
        # 知识段预算 ≈ 200-100-2-8 = 90；"大"×100 整条 ≈125 装不下被跳过，
        # 后续更短的 "小"（≈26）装入——相关度顺序贪心 + 跳过后仍尝试后续。
        profile = _profile(system_prompt="简。", context_length=200, max_tokens=100)
        hits = (
            KnowledgeHit(hit_id="big", content="大" * 100),
            KnowledgeHit(hit_id="small", content="小"),
        )
        result = assemble_context(_input(profile, knowledge_hits=hits))
        assert result.knowledge_included == ("small",)
        assert result.knowledge_dropped == 1

    def test_extra_system_notes_appended_after_knowledge(self) -> None:
        profile = _profile()
        result = assemble_context(
            _input(profile, extra_system_notes=("知识库暂无相关内容，请转人工。",))
        )
        system_contents = [m.content for m in result.messages if m.role is MessageRole.SYSTEM]
        assert system_contents[-1] == "知识库暂无相关内容，请转人工。"


class TestPassthroughMode:
    """直通模式（无 appCode）：messages 原样。"""

    def test_messages_passthrough_verbatim(self) -> None:
        history = _history(("历史问", "历史答"))
        result = assemble_context(_input(None, history=history, question="新问题"))
        assert [m.to_dict() for m in result.messages] == [
            {"role": "user", "content": "历史问"},
            {"role": "assistant", "content": "历史答"},
            {"role": "user", "content": "新问题"},
        ]
        assert result.prompt_budget is None
        assert result.dropped_history_turns == 0
        assert result.knowledge_included == ()

    def test_no_injection_no_truncation(self) -> None:
        big_history = _history(("问" * 500, "答" * 500))
        result = assemble_context(_input(None, history=big_history, question="问" * 500))
        assert len(result.messages) == 3  # 原样透传，不截断


def test_default_memory_rounds_constant() -> None:
    """领域回退常量存在且为正（应用配置缺省时的确定性行为）。"""
    assert DEFAULT_MEMORY_ROUNDS > 0
