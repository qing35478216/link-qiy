"""LinkAI 风格的应用 code 生成器。

对标物实测（linkai-screenshots/app-*-配置全文.txt）：
code 为 7 位随机字母数字，大小写混合，如 dWh6CGLY / eMk2NFfv / NReKRtSO。
专属链接形如 https://link-ai.tech/app/{code}。
"""

import secrets
import string

_ALPHABET = string.ascii_letters + string.digits  # 62 选 7，约 3.5 万亿组合


def generate_code(length: int = 7) -> str:
    """生成一个 7 位随机 code（secrets 保证密码学安全）。"""
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def generate_unique_code(is_taken, length: int = 7, max_attempts: int = 10) -> str:
    """生成不重复的 code；冲突时重试，超出次数则加长一位。

    is_taken: 回调，接收 code 返回 bool（True 表示已存在）。
    """
    for _ in range(max_attempts):
        code = generate_code(length)
        if not is_taken(code):
            return code
    # 极端情况：加长到 8 位再试
    return generate_unique_code(is_taken, length + 1, max_attempts)
