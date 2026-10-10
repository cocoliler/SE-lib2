from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from agent.schemas import TestCaseResult, TestExecutionResult


@dataclass
class ExecutionConfig:
    timeout_seconds: int = 30
    use_venv: bool = True


def _extract_pythonpath_for_target(target: Path) -> str:
    target = target.resolve()
    root = target if target.is_dir() else target.parent
    existing = os.environ.get("PYTHONPATH", "")
    parts = [str(root)]
    if existing:
        parts.append(existing)
    return os.pathsep.join(parts)


def _parse_unittest_output(stdout: str, stderr: str) -> list[TestCaseResult]:
    results: list[TestCaseResult] = []
    lines = (stdout + "\n" + stderr).splitlines()
    # unittest -v 输出格式：`test_foo (module.Class) ... ok|FAIL|ERROR`
    # 注意括号内是 unittest 的测试 id，形如 `module.Class.method` 或 `module.Class`
    pattern_end = re.compile(r"^(\S+)\s+\(([^()]+)\)\s+\.\.\.\s+(ok|FAIL|ERROR)$")
    for line in lines:
        m = pattern_end.match(line.strip())
        if not m:
            continue
        method, test_id, status = m.groups()
        # 如果括号内的 id 已经以 method 结尾，则直接使用 id（防止重复拼接）
        if test_id.endswith("." + method):
            full_name = test_id
        else:
            full_name = f"{test_id}.{method}"
        results.append(
            TestCaseResult(
                test_name=full_name,
                passed=(status == "ok"),
                error_message=None if status == "ok" else status,
            )
        )
    if results:
        return results

    # Fallback：匹配非 verbose 的 `ok|FAIL|ERROR: test_name (klass)`
    pattern_prefix = re.compile(r"^(ok|FAIL|ERROR):\s+(\S+)\s+\(([^()]+)\)")
    for line in lines:
        m = pattern_prefix.match(line.strip())
        if not m:
            continue
        status, method, test_id = m.groups()
        if test_id.endswith("." + method):
            full_name = test_id
        else:
            full_name = f"{test_id}.{method}"
        results.append(
            TestCaseResult(
                test_name=full_name,
                passed=(status == "ok"),
                error_message=None if status == "ok" else status,
            )
        )
    return results


def _count_tests_from_stdout(stdout: str, stderr: str | None = None) -> tuple[int, int, int]:
    total = passed = failed = 0
    combined = stdout
    if stderr:
        combined = stdout + "\n" + stderr
    for line in combined.splitlines():
        line = line.strip()
        m = re.search(r"Ran\s+(\d+)\s+test", line)
        if m:
            total = int(m.group(1))
        if re.search(r"^OK(\s*\(|$)", line) and total:
            passed = total
            failed = 0
        m = re.search(r"^FAILED\s*\((.+)\)", line)
        if m and total:
            detail = m.group(1)
            failures = re.search(r"failures=(\d+)", detail)
            errors = re.search(r"errors=(\d+)", detail)
            failed = (
                int(failures.group(1)) if failures else 0
            ) + (
                int(errors.group(1)) if errors else 0
            )
            passed = total - failed
    return total, passed, failed


def run_tests(
    test_file: Path | str,
    target_path: Path | str,
    config: ExecutionConfig | None = None,
) -> TestExecutionResult:
    config = config or ExecutionConfig()
    test_file = Path(test_file).resolve()
    target_path = Path(target_path).resolve()

    if not test_file.exists():
        return TestExecutionResult(
            test_file=str(test_file),
            exit_code=-1,
            stderr=f"测试文件不存在：{test_file}",
        )

    python = sys.executable
    env = os.environ.copy()
    env["PYTHONPATH"] = _extract_pythonpath_for_target(target_path)

    cmd = [python, "-m", "unittest", "-v", str(test_file)]
    started = time.monotonic()

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(target_path if target_path.is_dir() else target_path.parent),
            env=env,
            capture_output=True,
            text=True,
            timeout=config.timeout_seconds,
        )
        duration = time.monotonic() - started
    except subprocess.TimeoutExpired as exc:
        return TestExecutionResult(
            test_file=str(test_file),
            exit_code=-1,
            duration_seconds=config.timeout_seconds,
            stderr=f"测试执行超时（>{config.timeout_seconds}s）",
            stdout=(exc.stdout or b"").decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or ""),
        )
    except Exception as exc:
        return TestExecutionResult(
            test_file=str(test_file),
            exit_code=-1,
            stderr=f"执行异常：{exc}",
        )

    total, passed, failed = _count_tests_from_stdout(proc.stdout, proc.stderr)
    parsed = _parse_unittest_output(proc.stdout, proc.stderr)

    if total == 0 and parsed:
        total = len(parsed)
        passed = sum(1 for r in parsed if r.passed)
        failed = total - passed

    return TestExecutionResult(
        test_file=str(test_file),
        total_tests=total,
        passed_tests=passed,
        failed_tests=failed,
        duration_seconds=duration,
        results=parsed,
        stdout=proc.stdout,
        stderr=proc.stderr,
        exit_code=proc.returncode,
    )


def format_execution_report(result: TestExecutionResult) -> str:
    lines = [
        f"测试文件: {result.test_file}",
        f"退出码: {result.exit_code}",
        f"总用例: {result.total_tests}",
        f"通过: {result.passed_tests}",
        f"失败: {result.failed_tests}",
    ]
    if result.duration_seconds is not None:
        lines.append(f"耗时: {result.duration_seconds:.2f}s")
    if result.results:
        lines.append("")
        lines.append("用例详情:")
        for case in result.results:
            status = "PASS" if case.passed else "FAIL"
            extra = ""
            if not case.passed and case.error_message:
                extra = f"  ({case.error_message})"
            lines.append(f"  - [{status}] {case.test_name}{extra}")
    if result.stderr.strip():
        lines.append("")
        lines.append("STDERR 预览:")
        preview = "\n".join(result.stderr.strip().splitlines()[-30:])
        lines.append(preview)
    return "\n".join(lines)


def create_isolated_tempdir() -> Path:
    return Path(tempfile.mkdtemp(prefix="test-agent-"))
