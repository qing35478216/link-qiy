"""上下文装配——**纯函数**（领域层核心，可单测：输入集合确定则输出确定）。

装配四段（契约 docs/03 §3.4 + 工单 T-004 验收标准 1）：
    应用设定（system prompt，变量渲染后）
    + 知识库命中（本期无知识库服务，经 KnowledgeRetriever 端口占位，为空时走 miss 策略）
    + 记忆轮次（DB 历史，按 memoryRounds 截断为"轮"=user+assistant 对）
    + 本次问答（最后一条 user 消息）

token 预算（优先级从高到低，确定性贪心）：
    1. 系统提示词——必须整体装入（装不下 = 配置错误，抛 ContextOverflowError）
    2. 本次问答——必须整体装入（同上）
    3. 知识库命中——按相关度顺序贪心装入（跳过装不下的单条，继续尝试后续）
    4. 记忆轮次——从最新一轮起按轮贪心装入（遇到装不下的轮即停，更老的轮不再尝试）
    prompt 预算 = contextLength - maxTokens（为生成预留）。

直通模式（appCode 缺省）：messages 原样透传（OpenAI 兼容语义，不截断不注入）。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from linkai_runtime.domain.app_profile import AppProfile
from linkai_runtime.domain.chat import ChatMessage, MessageRole
from linkai_runtime.domain.errors import ContextOverflowError
from linkai_runtime.domain.tokens import estimate_messages_tokens, estimate_tokens

# ── 领域回退常量（应用配置缺省时使用；非业务硬编码——平台不预设最佳值，
#    这里只保证"配置缺失时行为确定且可解释"）─────────────────────
DEFAULT_CONTEXT_LENGTH = 4096
DEFAULT_MAX_TOKENS = 1024
DEFAULT_MEMORY_ROUNDS = 5

#: 变量占位符：{{ name }}（允许花括号内空白）
_VARIABLE_RE = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")

#: 知识库命中段的引导语（确定性模板）
_KNOWLEDGE_HEADER = "参考资料（按相关度排序，回答时引用编号）："


@dataclass(frozen=True, slots=True)
class KnowledgeHit:
    """一条知识库命中（知识服务落地后由 KnowledgeRetriever 产出）。"""

    hit_id: str
    content: str
    score: float = 0.0


@dataclass(frozen=True, slots=True)
class TokenBreakdown:
    """装配结果的 token 分布（观测用：进 trace step 的 plugin_output）。"""

    system: int
    knowledge: int
    history: int
    question: int
    total: int


@dataclass(frozen=True, slots=True)
class AssembledContext:
    """装配产物：最终 messages + 装配决策记录（可观测/可回放）。"""

    messages: tuple[ChatMessage, ...]
    prompt_budget: int | None
    tokens: TokenBreakdown
    dropped_history_turns: int
    knowledge_included: tuple[str, ...]
    knowledge_dropped: int


@dataclass(frozen=True, slots=True)
class AssemblyInput:
    """装配输入集合（确定此集合即确定输出）。"""

    profile: AppProfile | None
    history: tuple[ChatMessage, ...]
    knowledge_hits: tuple[KnowledgeHit, ...]
    question: str
    variables: Mapping[str, str]
    #: 请求显式传入的 maxTokens（优先于应用设定；应用设定缺省时用领域回退常量）
    max_tokens_override: int | None = None
    #: 附加系统注记（如知识库未命中的 miss 提示），插入在知识段之后、历史之前
    extra_system_notes: tuple[str, ...] = ()


def render_variables(template: str, variables: Mapping[str, str]) -> str:
    """渲染 {{ name }} 占位符（纯函数）。

    已知变量替换；未知占位符**原样保留**——静默替换为空会掩盖配置错误，
    保留字面量让人与模型都能看出"这里缺一个变量"。
    """
    return _VARIABLE_RE.sub(lambda m: variables.get(m.group(1), m.group(0)), template)


def assemble_context(inp: AssemblyInput) -> AssembledContext:
    """装配上下文（纯函数：无 IO、无时钟、无随机）。"""
    if inp.profile is None:
        return _passthrough(inp)
    return _app_mode(inp)


# ── 直通模式（OpenAI 兼容：messages 原样）────────────────────────


def _passthrough(inp: AssemblyInput) -> AssembledContext:
    messages = (*inp.history, ChatMessage(role=MessageRole.USER, content=inp.question))
    return AssembledContext(
        messages=messages,
        prompt_budget=None,
        tokens=TokenBreakdown(
            system=0,
            knowledge=0,
            history=estimate_messages_tokens(inp.history),
            question=estimate_tokens(inp.question),
            total=estimate_messages_tokens(messages),
        ),
        dropped_history_turns=0,
        knowledge_included=(),
        knowledge_dropped=0,
    )


# ── 应用模式（完整装配）────────────────────────────────────────


def _app_mode(inp: AssemblyInput) -> AssembledContext:
    profile = inp.profile
    assert profile is not None  # 调用方保证；mypy 收窄用

    # 变量合并：请求变量覆盖应用设定默认值
    merged_vars: dict[str, str] = dict(profile.default_variables())
    merged_vars.update(inp.variables)
    system_prompt = render_variables(profile.system_prompt or "", merged_vars)

    # 预算
    context_length = (
        profile.context_length if profile.context_length is not None else (DEFAULT_CONTEXT_LENGTH)
    )
    max_tokens = (
        inp.max_tokens_override
        if inp.max_tokens_override is not None
        else (profile.max_tokens if profile.max_tokens is not None else DEFAULT_MAX_TOKENS)
    )
    prompt_budget = context_length - max_tokens
    if prompt_budget <= 0:
        raise ContextOverflowError(
            f"上下文预算不足：contextLength={context_length} - maxTokens={max_tokens} "
            f"= {prompt_budget} <= 0（请调整应用设定或请求 maxTokens）"
        )

    # 必备段：系统提示词 + 本次问答
    tokens_system = estimate_tokens(system_prompt) if system_prompt else 0
    question_msg = ChatMessage(role=MessageRole.USER, content=inp.question)
    tokens_question = estimate_tokens(inp.question)
    if tokens_system + tokens_question > prompt_budget:
        raise ContextOverflowError(
            f"系统提示词({tokens_system}) + 本次问题({tokens_question}) 超出 prompt 预算 "
            f"{prompt_budget}（contextLength={context_length}, maxTokens={max_tokens}）"
        )
    remaining = prompt_budget - tokens_system - tokens_question

    # 知识库命中（相关度顺序贪心；单条装不下则跳过并继续尝试后续更短的）
    knowledge_text, included_ids, knowledge_dropped = _fill_knowledge(inp.knowledge_hits, remaining)
    tokens_knowledge = estimate_tokens(knowledge_text) if knowledge_text else 0
    remaining -= tokens_knowledge

    # 记忆轮次（memoryRounds 截断到"轮"；从最新一轮起贪心）
    memory_rounds = (
        profile.memory_rounds if profile.memory_rounds is not None else DEFAULT_MEMORY_ROUNDS
    )
    turns = _to_turns(inp.history)
    trimmed = turns[-memory_rounds:] if memory_rounds > 0 else []
    dropped_turns = len(turns) - len(trimmed)
    kept: list[tuple[ChatMessage, ...]] = []
    for turn in reversed(trimmed):  # 最新优先
        turn_tokens = estimate_messages_tokens(turn)
        if turn_tokens <= remaining:
            kept.append(turn)
            remaining -= turn_tokens
        else:
            break  # 确定性：更老的轮直接放弃，不再逐条尝试
    kept.reverse()  # 恢复时间顺序（旧 → 新）
    dropped_turns += len(trimmed) - len(kept)

    # 组装最终消息序列
    messages: list[ChatMessage] = []
    if system_prompt:
        messages.append(ChatMessage(role=MessageRole.SYSTEM, content=system_prompt))
    if knowledge_text:
        messages.append(ChatMessage(role=MessageRole.SYSTEM, content=knowledge_text))
    for note in inp.extra_system_notes:
        if note:
            messages.append(ChatMessage(role=MessageRole.SYSTEM, content=note))
    for turn in kept:
        messages.extend(turn)
    messages.append(question_msg)

    tokens_history = sum(estimate_messages_tokens(t) for t in kept)
    return AssembledContext(
        messages=tuple(messages),
        prompt_budget=prompt_budget,
        tokens=TokenBreakdown(
            system=tokens_system,
            knowledge=tokens_knowledge,
            history=tokens_history,
            question=tokens_question,
            total=estimate_messages_tokens(messages),
        ),
        dropped_history_turns=dropped_turns,
        knowledge_included=included_ids,
        knowledge_dropped=knowledge_dropped,
    )


def _fill_knowledge(
    hits: tuple[KnowledgeHit, ...], budget: int
) -> tuple[str, tuple[str, ...], int]:
    """知识库命中贪心装入。返回 (知识段文本, 装入的 hit_id, 跳过的条数)。"""
    if not hits or budget <= 0:
        return "", (), len(hits) if hits else 0
    included: list[str] = []
    current = _KNOWLEDGE_HEADER
    dropped = 0
    for hit in hits:
        candidate = f"{current}\n[{len(included) + 1}] {hit.content}"
        if estimate_tokens(candidate) <= budget:
            current = candidate
            included.append(hit.hit_id)
        else:
            dropped += 1  # 相关度更低或更短的后续条目仍有机会装入
    return (current, tuple(included), dropped) if included else ("", (), len(hits))


def _to_turns(history: tuple[ChatMessage, ...]) -> list[tuple[ChatMessage, ...]]:
    """把时间序历史切分为"轮"（user + 紧随的 assistant 为一轮）。

    从末尾向前配对：assistant 消息归属其前一条 user；孤立的 user 自成一轮
    （对话进行中被中断的场景）；tool 等异常角色并入当前轮尾部。
    """
    turns: list[tuple[ChatMessage, ...]] = []
    current: list[ChatMessage] = []
    for message in history:
        if message.role is MessageRole.USER and current:
            turns.append(tuple(current))
            current = [message]
        else:
            current.append(message)
    if current:
        turns.append(tuple(current))
    return turns
