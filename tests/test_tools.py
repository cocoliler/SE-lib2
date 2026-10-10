from __future__ import annotations

import ast
import unittest
from pathlib import Path

from tools.code_tool import analyze_path, analyze_source, format_function_summary
from tools.file_tool import read_python_files
from tools.test_tool import (
    ExecutionConfig,
    format_execution_report,
    run_tests,
)


class FileToolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.sample = Path(__file__).resolve().parent.parent / "examples" / "sample_module.py"

    def test_read_single_python_file(self) -> None:
        files = read_python_files(self.sample)
        self.assertEqual(len(files), 1)
        self.assertGreater(files[0].lines, 0)
        self.assertIn("def add(", files[0].content)

    def test_read_directory(self) -> None:
        files = read_python_files(self.sample.parent)
        self.assertGreaterEqual(len(files), 1)


class CodeToolTest(unittest.TestCase):
    def test_analyze_source_extracts_functions(self) -> None:
        src = "def foo(a: int, b: int) -> int:\n    return a + b\n"
        report = analyze_source(src, "x.py")
        self.assertTrue(report.syntax_valid)
        self.assertEqual(len(report.functions), 1)
        self.assertEqual(report.functions[0].name, "foo")
        self.assertIn("a: int", report.functions[0].args)

    def test_analyze_source_syntax_error(self) -> None:
        report = analyze_source("def foo(:\n", "x.py")
        self.assertFalse(report.syntax_valid)
        self.assertIsNotNone(report.syntax_error)

    def test_format_function_summary_contains_name(self) -> None:
        analyses = analyze_path(
            Path(__file__).resolve().parent.parent / "examples"
        )
        text = format_function_summary(analyses)
        self.assertIn("broken_max", text)


class TestToolTest(unittest.TestCase):
    def test_run_tests_smoke(self) -> None:
        """用当前这个 test 文件本身执行一次，确保能解析到结果结构。"""
        result = run_tests(Path(__file__), Path(__file__).resolve().parent.parent)
        self.assertIsNotNone(result.duration_seconds)
        self.assertGreaterEqual(result.total_tests, 0)
        text = format_execution_report(result)
        self.assertIn("总用例", text)


if __name__ == "__main__":
    unittest.main()
