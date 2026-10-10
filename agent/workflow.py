from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from agent.llm import LLMClient
from agent.prompts import ORCHESTRATOR_SYSTEM_PROMPT, build_orchestrator_prompt
from agent.schemas import (
    AgentRole,
    GeneratedTest,
    StepStatus,
    TestExecutionResult,
    WorkflowState,
    WorkflowStatus,
    WorkflowStep,
)
from agent.test_executor import ExecutionDiagnosis, TestExecutionAgent
from agent.test_generator import TestGenerationAgent
from tools.test_tool import format_execution_report


@dataclass
class WorkflowConfig:
    max_retries_on_generation: int = 1
    stop_on_all_passed: bool = True
    use_llm_orchestrator: bool = True
    output_dir: Path | str | None = None


@dataclass
class WorkflowReport:
    state: WorkflowState
    final_generated: GeneratedTest | None
    final_result: TestExecutionResult | None
    final_diagnosis: str

    def to_text(self) -> str:
        lines = ["=" * 60, "测试流程 Workflow 最终报告", "=" * 60, ""]
        lines.append(self.state.summary())
        lines.append("")
        lines.append("-" * 60)
        lines.append("最终生成的测试文件")
        lines.append("-" * 60)
        if self.final_generated:
            lines.append(f"路径: {self.final_generated.test_file_name}")
            if self.final_generated.reasoning:
                lines.append("设计说明:")
                lines.append(self.final_generated.reasoning)
        else:
            lines.append("(未成功生成)")

        lines.append("")
        lines.append("-" * 60)
        lines.append("最终执行结果")
        lines.append("-" * 60)
        if self.final_result:
            lines.append(format_execution_report(self.final_result))
        else:
            lines.append("(未执行)")

        lines.append("")
        lines.append("-" * 60)
        lines.append("执行诊断 / 修复建议")
        lines.append("-" * 60)
        lines.append(self.final_diagnosis or "(无)")

        lines.append("")
        lines.append("-" * 60)
        lines.append("Workflow 运行日志 (末尾 20 条)")
        lines.append("-" * 60)
        lines.extend(self.state.logs[-20:])

        return "\n".join(lines)


_DECISION_RE = re.compile(r"DECISION\s*:\s*(RETRY|FINISH)", re.IGNORECASE)
_REASON_RE = re.compile(r"REASON\s*:\s*(.*)", re.IGNORECASE)


class TestWorkflowOrchestrator:
    """编排：TestGenerationAgent -> TestExecutionAgent -> [重试判定] -> 最终报告。"""

    def __init__(
        self,
        llm: LLMClient,
        config: WorkflowConfig | None = None,
    ) -> None:
        self.llm = llm
        self.config = config or WorkflowConfig()
        self.generator = TestGenerationAgent(llm)
        self.executor = TestExecutionAgent(llm)

    def _create_state(self) -> WorkflowState:
        state = WorkflowState(run_id=f"run-{uuid.uuid4().hex[:8]}")
        state.steps = [
            WorkflowStep(
                name="generate_tests",
                agent_role=AgentRole.TEST_GENERATOR,
                max_retries=self.config.max_retries_on_generation,
            ),
            WorkflowStep(
                name="execute_tests",
                agent_role=AgentRole.TEST_EXECUTOR,
                max_retries=0,
            ),
        ]
        state.started_at = datetime.now()
        return state

    def _decide_with_llm(
        self,
        last_result: TestExecutionResult,
        retry_count: int,
        max_retries: int,
        notes: str,
    ) -> tuple[bool, str]:
        prompt = build_orchestrator_prompt(
            execution_report_text=format_execution_report(last_result),
            retry_count=retry_count,
            max_retries=max_retries,
            previous_decision_notes=notes,
        )
        try:
            raw = self.llm.complete(ORCHESTRATOR_SYSTEM_PROMPT, prompt, temperature=0.0)
        except Exception as exc:
            return False, f"LLM orchestrator 异常: {exc}"

        m_decision = _DECISION_RE.search(raw)
        m_reason = _REASON_RE.search(raw)
        decision = (m_decision.group(1).upper() == "RETRY") if m_decision else False
        reason = m_reason.group(1).strip() if m_reason else raw.strip()

        if decision and retry_count >= max_retries:
            decision = False
            reason = f"{reason} [已达到最大重试次数 {max_retries}，强制 FINISH]"

        return decision, reason

    def _heuristic_should_retry(
        self,
        result: TestExecutionResult,
        retry_count: int,
        max_retries: int,
    ) -> tuple[bool, str]:
        if retry_count >= max_retries:
            return False, f"达到最大重试次数 {max_retries}"
        if result.exit_code != 0 and result.total_tests == 0:
            return True, "所有测试均无法执行（语法/导入错误），需要重新生成"
        if result.total_tests == 0:
            return True, "未发现任何可执行测试，需要重新生成"
        return False, "进入最终诊断阶段"

    def run(
        self,
        target: Path | str,
        user_requirement: str = "为所有顶层函数生成单元测试，覆盖常规场景、边界条件和异常场景。",
        on_progress: Callable[[str], None] | None = None,
    ) -> WorkflowReport:
        target = Path(target).resolve()
        state = self._create_state()
        log = (
            (lambda msg: (on_progress(msg) if on_progress else None, state.add_log(msg)))
            if on_progress
            else (lambda msg: state.add_log(msg))
        )

        log(f"[Orchestrator] Workflow 启动: {state.run_id}, 目标: {target}")
        state.status = WorkflowStatus.RUNNING

        max_retries = self.config.max_retries_on_generation
        retry_count = 0
        decision_notes: list[str] = []
        final_generated: GeneratedTest | None = None
        final_diagnosis_obj: ExecutionDiagnosis | None = None

        gen_step = state.get_step("generate_tests")
        exec_step = state.get_step("execute_tests")

        while True:
            if gen_step:
                gen_step.status = StepStatus.RUNNING
                gen_step.started_at = datetime.now()
                gen_step.retry_count = retry_count
                state.current_step_index = 0

            log("[Orchestrator] STEP 1/2: 生成测试")
            history_notes = "\n".join(decision_notes)
            try:
                generated_list = self.generator.generate(
                    state=state,
                    target_path=target,
                    user_requirement=user_requirement,
                    output_dir=self.config.output_dir,
                    history_notes=history_notes,
                )
                final_generated = generated_list[-1]
                if gen_step:
                    gen_step.status = StepStatus.SUCCESS
                    gen_step.completed_at = datetime.now()
                    gen_step.output_data = {
                        "test_file": final_generated.test_file_name,
                        "target_functions": final_generated.target_functions,
                    }
            except Exception as exc:
                if gen_step:
                    gen_step.status = StepStatus.FAILED
                    gen_step.error = str(exc)
                    gen_step.completed_at = datetime.now()
                if retry_count < max_retries:
                    retry_count += 1
                    decision_notes.append(f"生成失败: {exc}")
                    log(f"[Orchestrator] 生成失败，准备重试 ({retry_count}/{max_retries})")
                    continue
                state.status = WorkflowStatus.FAILED
                state.completed_at = datetime.now()
                return WorkflowReport(
                    state=state,
                    final_generated=None,
                    final_result=None,
                    final_diagnosis=f"测试生成阶段持续失败：{exc}",
                )

            if exec_step:
                exec_step.status = StepStatus.RUNNING
                exec_step.started_at = datetime.now()
                state.current_step_index = 1

            log("[Orchestrator] STEP 2/2: 执行测试与诊断")
            try:
                diagnosis = self.executor.execute(state, final_generated, target)
                final_diagnosis_obj = diagnosis
                if exec_step:
                    exec_step.status = StepStatus.SUCCESS
                    exec_step.completed_at = datetime.now()
                    exec_step.output_data = {
                        "total": diagnosis.result.total_tests,
                        "passed": diagnosis.result.passed_tests,
                        "failed": diagnosis.result.failed_tests,
                        "exit_code": diagnosis.result.exit_code,
                    }
            except Exception as exc:
                if exec_step:
                    exec_step.status = StepStatus.FAILED
                    exec_step.error = str(exc)
                    exec_step.completed_at = datetime.now()
                state.status = WorkflowStatus.FAILED
                state.completed_at = datetime.now()
                return WorkflowReport(
                    state=state,
                    final_generated=final_generated,
                    final_result=None,
                    final_diagnosis=f"测试执行阶段异常：{exc}",
                )

            last_result = diagnosis.result

            if self.config.stop_on_all_passed and (
                last_result.total_tests > 0
                and last_result.failed_tests == 0
                and last_result.exit_code == 0
            ):
                log("[Orchestrator] 全部测试通过，提前结束。")
                break

            if self.config.use_llm_orchestrator:
                should_retry, reason = self._decide_with_llm(
                    last_result, retry_count, max_retries, "\n".join(decision_notes)
                )
            else:
                should_retry, reason = self._heuristic_should_retry(
                    last_result, retry_count, max_retries
                )

            log(f"[Orchestrator] 决策: {'RETRY' if should_retry else 'FINISH'} - {reason}")
            decision_notes.append(f"第{retry_count}轮 - {reason}")
            state.send_message(
                sender=AgentRole.ORCHESTRATOR,
                receiver=None,
                message_type="workflow_decision",
                payload={
                    "decision": "RETRY" if should_retry else "FINISH",
                    "reason": reason,
                    "retry_count": retry_count,
                },
            )

            if should_retry:
                retry_count += 1
                continue
            break

        if final_diagnosis_obj is None or final_generated is None:
            state.status = WorkflowStatus.FAILED
        elif (
            final_diagnosis_obj.result.total_tests > 0
            and final_diagnosis_obj.result.failed_tests == 0
        ):
            state.status = WorkflowStatus.SUCCESS
        elif final_diagnosis_obj.result.total_tests == 0:
            state.status = WorkflowStatus.FAILED
        else:
            state.status = WorkflowStatus.PARTIAL

        state.completed_at = datetime.now()
        log(f"[Orchestrator] Workflow 结束: {state.status.value}")

        return WorkflowReport(
            state=state,
            final_generated=final_generated,
            final_result=final_diagnosis_obj.result if final_diagnosis_obj else None,
            final_diagnosis=(
                final_diagnosis_obj.diagnosis_text if final_diagnosis_obj else "(无)"
            ),
        )
