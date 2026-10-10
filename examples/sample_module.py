"""
用于演示 Test Workflow Agent 的示例代码。

故意包含：
- 一些正确的函数，用于展示测试能通过；
- 一个带 Bug 的函数，用于演示失败用例；
- 一个需要异常测试的函数。
"""

from __future__ import annotations


def add(a: int, b: int) -> int:
    """返回两个整数之和。"""
    return a + b


def divide(numerator: float, denominator: float) -> float:
    """除法。分母为 0 时抛出 ZeroDivisionError。"""
    if denominator == 0:
        raise ZeroDivisionError("denominator cannot be zero")
    return numerator / denominator


def factorial(n: int) -> int:
    """计算 n! 。注意：只接受非负整数。"""
    if n < 0:
        raise ValueError("n must be non-negative")
    if n <= 1:
        return 1
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result


def safe_get(items: list[int], index: int, default: int = -1) -> int:
    """安全地访问 list 元素，越界返回 default。"""
    if not isinstance(index, int):
        raise TypeError("index must be int")
    if -len(items) <= index < len(items):
        return items[index]
    return default


def string_to_int_list(text: str) -> list[int]:
    """
    将逗号分隔的字符串转为整数列表。

    例："1, 2, 3" -> [1, 2, 3]
    空字符串返回空列表；非法的 token 直接忽略。
    """
    if not text:
        return []
    out: list[int] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            continue
    return out


def broken_max(a: int, b: int) -> int:
    """
    返回两者中较大的那个。

    （故意写错：当 a == b 时返回 a + 1 是错的；
    同时当 a < b 时也错误地返回 a。）
    该函数用于演示失败用例。
    """
    if a > b:
        return a
    if a == b:
        return a + 1
    return a


class Calculator:
    """示例类：一个简单计数器。"""

    def __init__(self, initial: int = 0) -> None:
        self.value = initial

    def add(self, n: int) -> "Calculator":
        self.value += n
        return self

    def subtract(self, n: int) -> "Calculator":
        self.value -= n
        return self

    def reset(self) -> None:
        self.value = 0

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Calculator):
            return NotImplemented
        return self.value == other.value
