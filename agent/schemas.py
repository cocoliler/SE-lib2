from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"


class AgentRole(str, Enum):
    TEST_GENERATOR = "test_generator"
    TEST_EXECUTOR = "test_executor"
    ORCHESTRATOR = "orchestrator"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class FileContent:
    path: str
    content: str
    lines: int


@dataclass
class FunctionSignature:
    name: str
    line_start: int
    line_end: int
    args: list[str]
    docstring: str | None = None


@dataclass
class CodeAnalysis:
    file_path: str
    functions: list[FunctionSignature] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    total_lines: int = 0
    syntax_valid: bool = True
    syntax_error: str | None = None


@dataclass
class GeneratedTest:
    test_file_name: str
    test_file_content: str
    target_functions: list[str] = field(default_factory=list)
    reasoning: str = ""


@dataclass
class TestCaseResult:
    test_name: str
    passed: bool
    duration_seconds: float | None = None
    error_message: str | None = None
    output: str | None = None


@dataclass
class TestExecutionResult:
    test_file: str
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    duration_seconds: float | None = None
    results: list[TestCaseResult] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0


@dataclass
class AgentMessage:
    sender: AgentRole
    receiver: AgentRole | None
    message_type: str
    payload: dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)

    def to_text(self) -> str:
        return f"[{self.timestamp.isoformat(timespec='seconds')}] {self.sender.value} -> {self.receiver.value if self.receiver else 'ALL'} [{self.message_type}]: {self.payload}"


@dataclass
class WorkflowStep:
    name: str
    agent_role: AgentRole
    status: StepStatus = StepStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    input_data: dict[str, Any] = field(default_factory=dict)
    output_data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    retry_count: int = 0
    max_retries: int = 1


@dataclass
class WorkflowState:
    run_id: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    steps: list[WorkflowStep] = field(default_factory=list)
    messages: list[AgentMessage] = field(default_factory=list)
    source_files: list[FileContent] = field(default_factory=list)
    code_analyses: list[CodeAnalysis] = field(default_factory=list)
    generated_tests: list[GeneratedTest] = field(default_factory=list)
    execution_results: list[TestExecutionResult] = field(default_factory=list)
    current_step_index: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    logs: list[str] = field(default_factory=list)

    def add_log(self, message: str) -> None:
        ts = datetime.now().isoformat(timespec="seconds")
        self.logs.append(f"[{ts}] {message}")

    def send_message(
        self,
        sender: AgentRole,
        receiver: AgentRole | None,
        message_type: str,
        payload: dict[str, Any],
    ) -> AgentMessage:
        msg = AgentMessage(
            sender=sender,
            receiver=receiver,
            message_type=message_type,
            payload=payload,
        )
        self.messages.append(msg)
        return msg

    def get_step(self, name: str) -> WorkflowStep | None:
        for step in self.steps:
            if step.name == name:
                return step
        return None

    def summary(self) -> str:
        lines = [
            f"Workflow Run: {self.run_id}",
            f"Status: {self.status.value}",
            f"Started: {self.started_at}",
            f"Completed: {self.completed_at}",
            f"Steps: {len(self.steps)}",
            f"Messages: {len(self.messages)}",
            f"Generated Tests: {len(self.generated_tests)}",
            f"Executions: {len(self.execution_results)}",
        ]
        for step in self.steps:
            lines.append(
                f"  - {step.name} ({step.agent_role.value}): {step.status.value}"
                + (f" [retry {step.retry_count}]" if step.retry_count else "")
                + (f" ERROR: {step.error}" if step.error else "")
            )
        return "\n".join(lines)
