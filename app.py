from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agent.llm import LLMClient
from agent.workflow import TestWorkflowOrchestrator, WorkflowConfig
from tools.code_tool import format_function_summary, analyze_path
from tools.test_tool import format_execution_report, run_tests


def _build_orchestrator(
    max_retries: int,
    no_llm_orchestrator: bool,
) -> TestWorkflowOrchestrator:
    llm = LLMClient.from_env()
    config = WorkflowConfig(
        max_retries_on_generation=max_retries,
        use_llm_orchestrator=not no_llm_orchestrator,
    )
    return TestWorkflowOrchestrator(llm=llm, config=config)


def cmd_run(
    target: str,
    requirement: str,
    max_retries: int,
    no_llm_orchestrator: bool,
    output_dir: str | None,
) -> int:
    path = Path(target)
    try:
        orch = _build_orchestrator(max_retries, no_llm_orchestrator)
        if output_dir:
            orch.config.output_dir = output_dir

        def progress(msg: str) -> None:
            print(msg, flush=True)

        report = orch.run(path, requirement, on_progress=progress)
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print()
    print(report.to_text())
    return 0


def cmd_analyze(target: str) -> int:
    try:
        analyses = analyze_path(Path(target))
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print(format_function_summary(analyses))
    return 0


def cmd_exec_test(test_file: str, target: str) -> int:
    try:
        result = run_tests(Path(test_file), Path(target))
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print(format_execution_report(result))
    return 0 if (result.total_tests > 0 and result.failed_tests == 0) else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test Workflow Agent (代码 → 生成测试 → 执行)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="运行完整 Workflow：生成测试 → 执行 → 诊断")
    run.add_argument("target", help="Python 文件或目录")
    run.add_argument(
        "--requirement",
        "-r",
        default="为所有顶层函数生成单元测试，覆盖常规场景、边界条件和异常场景。",
        help="测试生成要求",
    )
    run.add_argument(
        "--max-retries",
        type=int,
        default=1,
        help="测试生成阶段的最大重试次数（默认 1）",
    )
    run.add_argument(
        "--no-llm-orchestrator",
        action="store_true",
        help="不使用 LLM 做决策，仅基于启发式规则判定是否重试",
    )
    run.add_argument(
        "--output-dir",
        default=None,
        help="生成的测试文件输出目录（默认在目标目录下 tests_generated/）",
    )

    analyze = sub.add_parser("analyze", help="只运行函数签名分析（不调用 LLM）")
    analyze.add_argument("target")

    exec_cmd = sub.add_parser("exec-test", help="只执行已生成的测试文件")
    exec_cmd.add_argument("test_file", help="测试文件路径")
    exec_cmd.add_argument(
        "target",
        help="被测模块根目录（用于构造 PYTHONPATH）",
    )

    args = parser.parse_args()

    if args.command == "run":
        return cmd_run(
            args.target,
            args.requirement,
            args.max_retries,
            args.no_llm_orchestrator,
            args.output_dir,
        )
    if args.command == "analyze":
        return cmd_analyze(args.target)
    if args.command == "exec-test":
        return cmd_exec_test(args.test_file, args.target)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
