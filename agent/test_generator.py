from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from agent.llm import LLMClient
from agent.prompts import (
    TEST_GENERATOR_SYSTEM_PROMPT,
    build_generator_prompt,
)
from agent.schemas import (
    AgentRole,
    GeneratedTest,
    WorkflowState,
)
from tools.code_tool import format_function_summary
from tools.file_tool import read_python_files, write_test_file


_CODE_BLOCK_RE = re.compile(
    r"<TEST_CODE>\s*```(?:python)?\s*\n(.*?)\n```\s*</TEST_CODE>",
    re.DOTALL,
)
_FALLBACK_CODE_BLOCK_RE = re.compile(
    r"<TEST_CODE>\s*(.*?)\s*</TEST_CODE>",
    re.DOTALL,
)
_FILE_NAME_RE = re.compile(r"<TEST_FILE_NAME>\s*([\w\-\./\\]+\.py)\s*</TEST_FILE_NAME>")
_REASONING_RE = re.compile(r"<REASONING>\s*(.*?)\s*</REASONING>", re.DOTALL)


@dataclass
class _ParseResult:
    file_name: str
    code: str
    reasoning: str


def _parse_llm_output(raw: str) -> _ParseResult:
    m_name = _FILE_NAME_RE.search(raw)
    file_name = m_name.group(1).strip() if m_name else "test_generated.py"

    file_name = Path(file_name).name
    if not file_name.startswith("test_"):
        file_name = "test_" + file_name
    if not file_name.endswith(".py"):
        file_name += ".py"

    m_code = _CODE_BLOCK_RE.search(raw)
    if not m_code:
        m_code = _FALLBACK_CODE_BLOCK_RE.search(raw)
    if not m_code:
        fence = re.search(r"```(?:python)?\s*\n(.*?)\n```", raw, re.DOTALL)
        code = fence.group(1) if fence else raw
    else:
        code = m_code.group(1)
    code = code.strip()

    m_reason = _REASONING_RE.search(raw)
    reasoning = m_reason.group(1).strip() if m_reason else ""

    return _ParseResult(file_name=file_name, code=code, reasoning=reasoning)


def _module_hint_from_paths(files: list[str]) -> str:
    if not files:
        return ""
    if len(files) == 1:
        p = Path(files[0])
        return f"模块文件：{p.name}（stem={p.stem}）"
    paths = [Path(f) for f in files]
    try:
        common = Path(*paths[0].parts[:-1])
        while not all(str(p).startswith(str(common)) for p in paths):
            common = Path(*common.parts[:-1])
        return f"公共目录：{common}，包含模块：{', '.join(p.name for p in paths)}"
    except Exception:
        return "，".join(Path(f).name for f in files)


class TestGenerationAgent:
    """负责读取代码、分析函数签名并调用 LLM 生成 unittest 测试文件。"""

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def generate(
        self,
        state: WorkflowState,
        target_path: Path | str,
        user_requirement: str = "为所有顶层函数生成单元测试，覆盖常规场景、边界条件和异常场景。",
        output_dir: Path | str | None = None,
        history_notes: str = "",
    ) -> list[GeneratedTest]:
        target_path = Path(target_path).resolve()

        state.add_log(f"[TestGen] 开始读取目标: {target_path}")
        files = read_python_files(target_path)
        state.source_files = files
        state.send_message(
            sender=AgentRole.TEST_GENERATOR,
            receiver=AgentRole.TEST_EXECUTOR,
            message_type="source_files_ready",
            payload={"count": len(files), "paths": [f.path for f in files]},
        )

        from tools.code_tool import analyze_source
        analyses = [analyze_source(f.content, f.path) for f in files]
        state.code_analyses = analyses
        function_summary = format_function_summary(analyses)

        sources_text = "\n\n".join(
            f"===== {f.path} =====\n{f.content}" for f in files
        )
        module_hint = _module_hint_from_paths([f.path for f in files])

        prompt = build_generator_prompt(
            target_module_hint=module_hint,
            source_files_text=sources_text,
            function_summary=function_summary,
            user_requirement=user_requirement,
            history_notes=history_notes,
        )

        state.add_log("[TestGen] 调用 LLM 生成测试...")
        raw = self.llm.complete(TEST_GENERATOR_SYSTEM_PROMPT, prompt, temperature=0.2)

        parsed = _parse_llm_output(raw)

        output_dir = (
            Path(output_dir).resolve()
            if output_dir
            else target_path if target_path.is_dir() else target_path.parent
        ) / "tests_generated"

        written_path = write_test_file(parsed.code, output_dir / parsed.file_name)
        target_functions = [f.name for a in analyses for f in a.functions]

        generated = GeneratedTest(
            test_file_name=str(written_path),
            test_file_content=parsed.code,
            target_functions=target_functions,
            reasoning=parsed.reasoning,
        )
        state.generated_tests.append(generated)

        state.send_message(
            sender=AgentRole.TEST_GENERATOR,
            receiver=AgentRole.TEST_EXECUTOR,
            message_type="generated_tests_ready",
            payload={
                "test_file": generated.test_file_name,
                "target_functions": target_functions,
                "reasoning": parsed.reasoning,
            },
        )
        state.add_log(f"[TestGen] 生成测试文件: {generated.test_file_name}")

        return [generated]
