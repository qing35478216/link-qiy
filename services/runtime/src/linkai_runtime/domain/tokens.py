"""Token 估算——纯函数（领域层，可单测，确定性输出）。

选型记录（AGENTS.md 铁律 8，详见 services/runtime/ADOPTED-TOOLS.md）：
- 候选 A：tiktoken（MIT，OpenAI 官方 BPE）——精确但只覆盖 OpenAI 系词表；
  runtime 经 model-proxy 路由多厂商（deepseek/qwen/glm/anthropic…），
  单一分词器无法覆盖全部模型族，按模型切换分词器等于把厂商知识搬进 runtime。
- 候选 B：HuggingFace tokenizers / SentencePiece——同样按模型族分裂。
- 候选 C（采用）：厂商无关的启发式估算——CJK 字符≈1 token/字、其余≈1 token/4 字符，
  零依赖、确定性、与 model-proxy 既有 HeuristicTokenEstimator 同口径。

Phase 0 该估算只用于**上下文预算截断**（装配决策），不用于计费
（计费用量以 model-proxy 回传的真实 usage 为准）；误差可接受。
按模型精确化（tiktoken 按 model_code 分派）列为后续优化。
"""

from __future__ import annotations

import math

from linkai_runtime.domain.chat import ChatMessage

#: 每条消息的固定开销（OpenAI chat 惯例：role/name 等结构位）
MESSAGE_OVERHEAD_TOKENS = 4

# ── CJK 判别区间 ──────────────────────────────────────────────
# CJK 统一表意文字（基本 + 扩展A）、兼容表意、日文假名、韩文音节、
# 全角形式（标点/字母）、CJK 符号与标点、注音/彝文等表意扩展区。
_CJK_RANGES: tuple[tuple[int, int], ...] = (
    (0x1100, 0x115F),  # 韩文字头
    (0x2E80, 0x2EFF),  # CJK 部首补充
    (0x3000, 0x303F),  # CJK 符号与标点
    (0x3040, 0x30FF),  # 日文平假名/片假名
    (0x3130, 0x318F),  # 韩文兼容字母
    (0x3400, 0x4DBF),  # CJK 统一表意文字扩展 A
    (0x4E00, 0x9FFF),  # CJK 统一表意文字
    (0xA000, 0xA4CF),  # 彝文
    (0xAC00, 0xD7AF),  # 韩文音节
    (0xF900, 0xFAFF),  # CJK 兼容表意文字
    (0xFE30, 0xFE4F),  # CJK 兼容形式
    (0xFF00, 0xFFEF),  # 全角形式（半角变体）
    (0x20000, 0x2A6DF),  # CJK 扩展 B
    (0x1F300, 0x1FAFF),  # emoji/符号扩展（按 1 token 近似）
)

#: 非 CJK 字符每 token 的字符数（英文/数字/代码经验值）
_CHARS_PER_TOKEN_NON_CJK = 4


def _is_cjk(ch: str) -> bool:
    code = ord(ch)
    return any(lo <= code <= hi for lo, hi in _CJK_RANGES)


def estimate_tokens(text: str) -> int:
    """估算一段文本的 token 数（纯函数：同输入同输出）。"""
    if not text:
        return 0
    cjk = 0
    other = 0
    for ch in text:
        if _is_cjk(ch):
            cjk += 1
        else:
            other += 1
    return max(1, cjk + math.ceil(other / _CHARS_PER_TOKEN_NON_CJK))


def estimate_messages_tokens(messages: tuple[ChatMessage, ...] | list[ChatMessage]) -> int:
    """估算一组消息的 token 总数（含每条消息的结构开销）。"""
    return sum(estimate_tokens(m.content) + MESSAGE_OVERHEAD_TOKENS for m in messages)
