# -*- coding: utf-8 -*-
"""sample_module 的 unittest 单元测试。"""

import importlib.util
import os
import sys
import unittest


def _load_sample_module():
    """定位并加载被测模块 sample_module，保证导入路径正确。"""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        here,
        os.path.join(here, "examples"),
        os.path.join(os.path.dirname(here), "examples"),
        "/home/cocoli/1/code/se/project1/se-lib2/examples",
    ]
    for directory in candidates:
        path = os.path.join(directory, "sample_module.py")
        if os.path.isfile(path):
            if directory not in sys.path:
                sys.path.insert(0, directory)
            return __import__("sample_module")

    # 兜底：直接按给定的绝对文件路径加载
    fallback = "/home/cocoli/1/code/se/project1/se-lib2/examples/sample_module.py"
    spec = importlib.util.spec_from_file_location("sample_module", fallback)
    module = importlib.util.module_from_spec(spec)
    sys.modules["sample_module"] = module
    spec.loader.exec_module(module)
    return module


sample_module = _load_sample_module()

add = sample_module.add
divide = sample_module.divide
factorial = sample_module.factorial
safe_get = sample_module.safe_get
string_to_int_list = sample_module.string_to_int_list
broken_max = sample_module.broken_max
Calculator = sample_module.Calculator


class TestAdd(unittest.TestCase):
    """add 函数测试。"""

    def test_add_positive(self):
        # 常规正数相加
        self.assertEqual(add(2, 3), 5)

    def test_add_negative(self):
        # 两个负数相加
        self.assertEqual(add(-2, -3), -5)

    def test_add_mixed_signs(self):
        # 一正一负
        self.assertEqual(add(-5, 3), -2)

    def test_add_zero(self):
        # 零值边界
        self.assertEqual(add(0, 0), 0)


class TestDivide(unittest.TestCase):
    """divide 函数测试。"""

    def test_divide_normal(self):
        # 常规整除
        self.assertEqual(divide(10, 2), 5.0)

    def test_divide_float_result(self):
        # 结果为浮点数
        self.assertAlmostEqual(divide(7.0, 2.0), 3.5)

    def test_divide_negative(self):
        # 负数除法
        self.assertEqual(divide(-6, 3), -2.0)

    def test_divide_numerator_zero(self):
        # 分子为 0 的边界
        self.assertEqual(divide(0, 5), 0.0)

    def test_divide_by_zero_raises(self):
        # 分母为 0 时抛出 ZeroDivisionError
        with self.assertRaises(ZeroDivisionError):
            divide(1, 0)

    def test_divide_by_zero_float_raises(self):
        # 分母为 0.0 时同样抛出 ZeroDivisionError
        with self.assertRaises(ZeroDivisionError):
            divide(1.0, 0.0)

    def test_divide_by_zero_error_message(self):
        # 验证异常消息
        with self.assertRaisesRegex(ZeroDivisionError, "denominator cannot be zero"):
            divide(1, 0)


class TestFactorial(unittest.TestCase):
    """factorial 函数测试。"""

    def test_factorial_zero(self):
        # 0! == 1 的边界
        self.assertEqual(factorial(0), 1)

    def test_factorial_one(self):
        # 1! == 1 的边界
        self.assertEqual(factorial(1), 1)

    def test_factorial_two(self):
        # 2! == 2
        self.assertEqual(factorial(2), 2)

    def test_factorial_common(self):
        # 常规阶乘
        self.assertEqual(factorial(5), 120)
        self.assertEqual(factorial(6), 720)

    def test_factorial_negative_raises_value_error(self):
        # 负数应抛出 ValueError
        with self.assertRaises(ValueError):
            factorial(-1)

    def test_factorial_negative_error_message(self):
        # 验证异常消息
        with self.assertRaisesRegex(ValueError, "n must be non-negative"):
            factorial(-10)


class TestSafeGet(unittest.TestCase):
    """safe_get 函数测试。"""

    def setUp(self):
        self.items = [10, 20, 30]

    def test_get_first_element(self):
        # 正索引访问
        self.assertEqual(safe_get(self.items, 0), 10)

    def test_get_middle_element(self):
        # 正索引访问中间元素
        self.assertEqual(safe_get(self.items, 1), 20)

    def test_get_last_element_by_positive_index(self):
        # 正索引访问最后一个元素
        self.assertEqual(safe_get(self.items, 2), 30)

    def test_get_negative_index(self):
        # 负索引访问
        self.assertEqual(safe_get(self.items, -1), 30)
        self.assertEqual(safe_get(self.items, -3), 10)

    def test_out_of_range_positive_returns_default(self):
        # 正越界返回默认值
        self.assertEqual(safe_get(self.items, 3), -1)

    def test_out_of_range_negative_returns_default(self):
        # 负越界返回默认值
        self.assertEqual(safe_get(self.items, -4), -1)

    def test_custom_default_value(self):
        # 指定 default 参数时返回该值
        self.assertEqual(safe_get(self.items, 99, default=0), 0)

    def test_empty_list_returns_default(self):
        # 空列表中任何索引都越界，返回默认值
        self.assertEqual(safe_get([], 0), -1)
        self.assertEqual(safe_get([], -1, default=42), 42)

    def test_non_int_index_raises_type_error(self):
        # 非 int 索引抛出 TypeError
        with self.assertRaises(TypeError):
            safe_get(self.items, "1")

    def test_non_int_index_error_message(self):
        # 验证 TypeError 异常消息
        with self.assertRaisesRegex(TypeError, "index must be int"):
            safe_get(self.items, "1")


class TestStringToIntList(unittest.TestCase):
    """string_to_int_list 函数测试。"""

    def test_normal_input(self):
        # 常规逗号分隔字符串
        self.assertEqual(string_to_int_list("1, 2, 3"), [1, 2, 3])

    def test_empty_string(self):
        # 空字符串返回空列表
        self.assertEqual(string_to_int_list(""), [])

    def test_whitespace_only(self):
        # 纯空白字符串返回空列表
        self.assertEqual(string_to_int_list("   "), [])

    def test_empty_tokens_are_skipped(self):
        # 空 token 被忽略
        self.assertEqual(string_to_int_list("1,,2, ,3"), [1, 2, 3])

    def test_invalid_tokens_are_ignored(self):
        # 非法 token 被忽略
        self.assertEqual(string_to_int_list("1,abc,3"), [1, 3])

    def test_float_tokens_are_ignored(self):
        # 浮点 token 不是合法 int，被忽略
        self.assertEqual(string_to_int_list("1,2.5,3"), [1, 3])

    def test_negative_numbers(self):
        # 支持负数
        self.assertEqual(string_to_int_list("-1,-2,3"), [-1, -2, 3])

    def test_spaces_around_numbers(self):
        # 数字前后带空格应被正确解析
        self.assertEqual(string_to_int_list(" 10 , 20 ,30 "), [10, 20, 30])

    def test_single_number(self):
        # 单个数字
        self.assertEqual(string_to_int_list("42"), [42])


class TestBrokenMax(unittest.TestCase):
    """broken_max 函数测试。

    该函数在源码中明确标注为“故意写错，用于演示失败用例”。
    对正确的分支编写普通用例；对错误分支按文档期望编写断言并标记
    expectedFailure，以便清晰暴露缺陷且不污染整体测试结果。
    """

    def test_max_first_larger(self):
        # a > b 时返回 a（实现正确）
        self.assertEqual(broken_max(5, 3), 5)

    @unittest.expectedFailure
    def test_max_second_larger(self):
        # a < b 时应返回 b，实际实现错误地返回 a
        self.assertEqual(broken_max(3, 5), 5)

    @unittest.expectedFailure
    def test_max_equal_values(self):
        # a == b 时应返回 a（或 b），实际实现返回 a + 1
        self.assertEqual(broken_max(4, 4), 4)


class TestCalculator(unittest.TestCase):
    """Calculator 类测试。"""

    def test_default_initial_value(self):
        # 未传参数时初始值为 0
        self.assertEqual(Calculator().value, 0)

    def test_custom_initial_value(self):
        # 指定初始值
        self.assertEqual(Calculator(10).value, 10)

    def test_add_returns_self(self):
        # add 返回 self，支持链式调用
        calc = Calculator(0)
        self.assertIs(calc.add(5), calc)
        self.assertEqual(calc.value, 5)

    def test_subtract_returns_self(self):
        # subtract 返回 self，支持链式调用
        calc = Calculator(10)
        self.assertIs(calc.subtract(3), calc)
        self.assertEqual(calc.value, 7)

    def test_chained_operations(self):
        # 链式调用 add/subtract
        calc = Calculator(1).add(2).subtract(1).add(10)
        self.assertEqual(calc.value, 12)

    def test_reset(self):
        # reset 将值重置为 0
        calc = Calculator(100)
        result = calc.reset()
        self.assertIsNone(result)
        self.assertEqual(calc.value, 0)

    def test_equality_same_value(self):
        # 两个值相等的 Calculator 相等
        self.assertEqual(Calculator(5), Calculator(5))

    def test_inequality_different_value(self):
        # 两个值不相等的 Calculator 不相等
        self.assertNotEqual(Calculator(5), Calculator(6))

    def test_equality_with_non_calculator(self):
        # 与其它类型比较返回 False（__eq__ 返回 NotImplemented）
        self.assertFalse(Calculator(5) == 5)
        self.assertFalse(Calculator(5) == "5")

    def test_self_equality(self):
        # 自身与自身相等
        calc = Calculator(7)
        self.assertEqual(calc, calc)


if __name__ == "__main__":
    unittest.main()