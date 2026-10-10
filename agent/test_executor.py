from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent.llm import LLMClient
from agent.prompts import (
    TEST_EXECUTOR_SYSTEM_PROMPT,
    build_executor_prompt,
)
from agent.schemas import (
    AgentRole,
    GeneratedTest,
    TestExecutionResult,
    WorkflowState,
)
from tools.test_tool import (
    ExecutionConfig,
    format_execution_report,
    run_tests,
)


@dataclass
class ExecutionDiagnosis:
    result: TestExecutionResult
    diagnosis_text: str

    @property
    def has_runtime_error(self) -> bool:
        return (
            self.result.exit_code != 0
            and self.result.total_tests == 0
        ) or any(
            not r.passed and "error" in (r.test_name.lower() + (r.error_message or "").lower())
            for r in self.result.results
        )

    @property
    def all_passed(self) -> bool:
        return (
            self.result.total_tests > 0
            and self.result.failed_tests == 0
            and self.result.exit_code == 0
        )


class TestExecutionAgent:
    """负责运行测试、收集执行结果并调用 LLM 给出诊断。"""

    def __init__(
        self,
        llm: LLMClient,
        execution_config: ExecutionConfig | None = None,
    ) -> None:
        self.llm = llm
        self.execution_config = execution_config or ExecutionConfig()

    def execute(
        self,
        state: WorkflowState,
        generated: GeneratedTest,
        target_path: Path | str,
    ) -> ExecutionDiagnosis:
        target_path = Path(target_path).resolve()

        state.send_message(
            sender=AgentRole.TEST_EXECUTOR,
            receiver=AgentRole.TEST_GENERATOR,
            message_type="start_execution",
            payload={"test_file": generated.test_file_name},
        )
        state.add_log(f"[TestExec] 运行测试: {generated.test_file_name}")

        result = run_tests(
            generated.test_file_name,
            target_path,
            config=self.execution_config,
        )
        state.execution_results.append(result)

        report = format_execution_report(result)
        state.add_log(f"[TestExec] 结果: 通过 {result.passed_tests}/{result.total_tests}")

        sources_text = "\n\n".join(
            f"===== {f.path} =====\n{f.content}" for f in state.source_files
        )
        prompt = build_executor_prompt(
            source_files_text=sources_text,
            generated_test_code=generated.test_file_content,
            execution_report_text=report,
        )

        state.add_log("[TestExec] 调用 LLM 生成执行诊断...")
        try:
            diagnosis = self.llm.complete(
                TEST_EXECUTOR_SYSTEM_PROMPT, prompt, temperature=0.1
            )
        except Exception as exc:
            diagnosis = f"(LLM 调用失败，保留原始执行报告)\n错误：{exc}\n\n{report}"

        state.send_message(
            sender=AgentRole.TEST_EXECUTOR,
            receiver=AgentRole.ORCHESTRATOR,
            message_type="execution_done",
            payload={
                "total": result.total_tests,
                "passed": result.passed_tests,
                "failed": result.failed_tests,
                "exit_code": result.exit_code,
                "has_runtime_error": (
                    result.exit_code != 0 and result.total_tests == 0
                ),
            },
        )

        return ExecutionDiagnosis(result=result, diagnosis_text=diagnosis)
