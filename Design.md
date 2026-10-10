# Test Workflow Agent 设计文档

## 1. 项目背景

本项目对应 Homework 2 的 **测试流程** 方向，流程描述为：

```
代码 → 生成测试 → 执行
```

Agent 组成：

```
测试生成Agent（TestGenerationAgent）+ 测试执行Agent（TestExecutionAgent）
+ Workflow 编排器（Orchestrator）
```

课程要求包括：

- 至少 2 个 Agent 协作完成一个完整流程
- 实现 Agent 间的消息传递或状态共享
- 支持基本的流程控制（顺序执行）
- MVP 可运行即可，不需要复杂调度
- 推荐支持条件分支 / 循环 / 重试 / 执行日志 / 状态追踪 / 错误恢复

本项目实现了：

1. **TestGenerationAgent**：读取代码 → AST 分析函数签名 → 调用 LLM 生成 unittest 风格测试
2. **TestExecutionAgent**：调用测试执行工具运行生成的测试 → 汇总执行报告 → 调用 LLM 生成失败诊断与修复建议
3. **TestWorkflowOrchestrator**：负责 Workflow 编排，按顺序执行上述两个 Agent，并根据执行结果做 **条件分支（FINISH / RETRY）** 与 **生成阶段有限次重试**

---

## 2. 总体架构

```text
┌──────────────────────────────────────────────────────────┐
│                        CLI / App.py                      │
└──────────────────────────────┬───────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────┐
│            TestWorkflowOrchestrator (编排器)              │
│  顺序执行 / 条件分支(FINISH,RETRY) / 重试上限 / 状态追踪  │
└──────────┬───────────────────────────────────────┬────────┘
           │                                       │
           ▼                                       ▼
┌─────────────────────────┐         ┌─────────────────────────┐
│  TestGenerationAgent    │ 消息    │  TestExecutionAgent     │
│  （测试生成 Agent）      │◄───────►│  （测试执行 Agent）      │
│  - 读取代码             │ 共享    │  - 运行测试(unittest)    │
│  - AST 分析函数签名     │ 状态    │  - 解析执行结果          │
│  - 构造 Prompt          │ Workflow│  - 诊断失败原因          │
│  - 写入测试文件         │ State   │  - 生成修复建议          │
└──────────┬──────────────┘         └────────────┬────────────┘
           │                                     │
           ▼                                     ▼
┌───────────────────────┐         ┌───────────────────────────┐
│   Tools / 工具层      │         │      LLM 客户端           │
│ - file_tool.py        │         │  (带指数退避重试)         │
│ - code_tool.py (AST)  │         └────────────▲──────────────┘
│ - test_tool.py (执行) │                      │
└───────────────────────┘                      │
                                               │
                                     ┌─────────┴─────────┐
                                     │  LLM Provider     │
                                     │ (OpenAI 兼容接口) │
                                     └───────────────────┘
```

核心协作模型：

- **共享状态**：所有 Agent 共享同一个 `WorkflowState`，其中记录 source_files / code_analyses / generated_tests / execution_results / messages / logs / steps 等。
- **显式消息**：Agent 之间通过 `state.send_message(sender, receiver, type, payload)` 记录结构化事件，便于后续回放与审计。
- **顺序 + 条件分支**：Orchestrator 首先依次触发 生成 → 执行；随后使用 **启发式规则** 或 **LLM** 决策是否 RETRY（重新生成）或 FINISH（输出最终报告）。

---

## 3. Workflow 详细流程

```text
[启动]
  │
  ▼
创建 WorkflowState (run_id, steps=[])
  │
  ▼
┌───────────────────────────────────────────────────────┐
│  Step 1: generate_tests (TestGenerationAgent)         │
│  1.1 读取目标 Python 文件                              │
│  1.2 AST 分析：函数签名 / 参数 / docstring / 类 / 导入 │
│  1.3 构造 Prompt：模块名提示 + 函数摘要 + 源码 + 历史  │
│  1.4 调用 LLM → 解析 <TEST_FILE_NAME>/<REASONING>/    │
│                  <TEST_CODE>                          │
│  1.5 写入 tests_generated/ 目录                       │
│  1.6 发送消息：generated_tests_ready → TestExecutor    │
└───────────────────────────────────────────────────────┘
  │  失败？──是──→ 重试次数 < max？→ 重试 Step1
  │                    └─ 否 → Workflow FAILED
  ▼
┌───────────────────────────────────────────────────────┐
│  Step 2: execute_tests (TestExecutionAgent)           │
│  2.1 设置 PYTHONPATH 指向被测根目录                    │
│  2.2 subprocess 调用 `python -m unittest -v test_file`│
│  2.3 解析 stdout/stderr → total/passed/failed/详情    │
│  2.4 调用 LLM 结合 源码+测试代码+执行结果 做诊断       │
│  2.5 发送消息：execution_done → Orchestrator           │
└───────────────────────────────────────────────────────┘
  │
  ▼
┌───────────────────────────────────────────────────────┐
│  Orchestrator 决策 (条件分支)                         │
│                                                       │
│  若 stop_on_all_passed 且 全部通过：                  │
│       → FINISH (SUCCESS)                              │
│                                                       │
│  否则：                                               │
│   - 使用 LLM Orchestrator Prompt 判断：RETRY / FINISH │
│   - 或使用启发式：0 条执行 → RETRY，否则 FINISH        │
│                                                       │
│  RETRY? ──是──→ retry_count < max_retries?            │
│     │               │是 → 回到 Step1                  │
│     │               └─ 否 → FINISH (PARTIAL/FAILED)   │
│     └─ 否 → FINISH                                    │
└───────────────────────────────────────────────────────┘
  │
  ▼
[生成 WorkflowReport 并返回]
```

---

## 4. 共享状态 / 消息传递设计

### 4.1 WorkflowState 核心字段

| 字段 | 用途 |
|---|---|
| run_id | 每次运行唯一 ID，便于追踪 |
| status | pending / running / success / failed / partial |
| steps | 每个 Step 的 name、agent_role、status、耗时、输入输出、错误、重试次数 |
| messages | Agent 间发送的结构化消息列表（sender / receiver / type / payload / 时间） |
| source_files | 读取到的原始代码 |
| code_analyses | AST 分析结果（函数签名等） |
| generated_tests | 每一轮生成的测试文件及其内容、设计说明 |
| execution_results | 每一轮执行结果（总数 / 通过 / 失败 / 各用例详情 / stdout / stderr） |
| current_step_index / started_at / completed_at | 时间线追踪 |
| logs | 人类可读的运行日志，用于最终报告 |

### 4.2 典型消息流

```
TEST_GENERATOR -> TEST_EXECUTOR  [source_files_ready]
TEST_GENERATOR -> TEST_EXECUTOR  [generated_tests_ready]
TEST_EXECUTOR -> TEST_GENERATOR  [start_execution]
TEST_EXECUTOR -> ORCHESTRATOR    [execution_done]
ORCHESTRATOR -> ALL              [workflow_decision]
```

每条消息都带时间戳和结构化 payload，方便后续 UI 渲染或回放。

---

## 5. Agent 设计

### 5.1 TestGenerationAgent

输入：
- target_path（文件或目录）
- user_requirement（测试生成要求）
- history_notes（前序轮次的决策原因，提示 LLM 修复问题）

调用的工具：
- `read_python_files`：安全读取 .py 文件
- `analyze_source`：AST 提取函数签名 / 参数 / docstring
- `write_test_file`：将生成的代码写入 tests_generated/

Prompt 构造要点：
- 提供**模块名提示**，便于 LLM 写出正确的 import 语句；
- 提供**确定性的函数摘要**，避免 LLM 漏函数或编造签名；
- 提供**前一轮执行反馈**，使重试生成能针对性修复（例如 import 路径错了 / 语法错了）。

输出格式强制约束：
```
<TEST_FILE_NAME>  test_xxx.py </TEST_FILE_NAME>
<REASONING> 设计说明 </REASONING>
<TEST_CODE> ```python ... ``` </TEST_CODE>
```
代码中提供了多重正则的 fallback 解析器，即使 LLM 稍有偏差也尽量恢复。

### 5.2 TestExecutionAgent

输入：
- GeneratedTest（测试文件路径 + 代码内容 + 目标函数列表）
- target_path（被测根目录，用于 PYTHONPATH）

调用的工具：
- `run_tests`：subprocess 调用 `python -m unittest -v`，带超时保护；
- `format_execution_report`：将 TestExecutionResult 渲染为易读文本，再喂给诊断 LLM。

诊断阶段 Prompt 明确引导：
- 区分 **代码 Bug** 和 **测试构造问题**；
- 对每个失败用例给出修复建议（优先改测试或优先改代码）；
- 给出后续测试增补建议（覆盖遗漏场景）。

### 5.3 Orchestrator（不是独立 Agent，但承担编排职责）

两种决策模式：

1. **LLM 模式（默认）**：使用 `ORCHESTRATOR_SYSTEM_PROMPT` 让模型判断 RETRY / FINISH，并给出原因。模型被明确要求只在 0 用例可执行 / 测试明显构造错误 时建议 RETRY，真正的代码 Bug 不应反复重试生成测试。
2. **启发式模式（`--no-llm-orchestrator`）**：
   - `exit_code != 0 && total == 0` → RETRY（完全不能运行）
   - `total == 0` → RETRY（没解析到用例）
   - 否则 → FINISH

两种模式共同遵守：**retry_count 达到上限后强制 FINISH**（循环控制）。

---

## 6. 错误处理与恢复机制

- **LLM 层**：`llm.py` 实现 `max_retries=3` 的指数退避重试（1s / 2s / 4s）。
- **测试生成层**：当生成的测试无法运行时，Orchestrator 允许最多 `max_retries_on_generation` 次重新生成，并把上一轮执行 STDERR 注入 history_notes。
- **执行层**：subprocess 调用带 `timeout_seconds` 防挂死；捕获异常统一落到 `TestExecutionResult`，而不是冒泡崩溃。
- **工作流层**：每一步的异常都会记录到 step.error，并触发 RETRY（若仍有次数）或把整个 workflow 标记为 FAILED，同时保证最终报告仍能输出，便于排查。

---

## 7. 与评分标准的对应关系

| 评分维度 | 权重 | 项目实现 |
|---|---|---|
| 流程完整性 | 40% | 端到端跑通：读取代码 → AST → 生成测试 → 写文件 → 执行 → 诊断 → 报告；含失败重试回路 |
| Agent 协作 | 30% | 2 个 Agent + 1 编排器；通过 WorkflowState 共享数据，通过结构化消息 AgentMessage 通信，含时间戳与 payload |
| 可扩展性 | 20% | 模块化拆分：schemas / llm / prompts / test_generator / test_executor / workflow / tools；新增 Agent 只需遵循相同的 state 读写约定，Workflow step 可按同样模式扩展 |
| 文档 | 10% | README.md + Design.md + 流程图 + 使用示例 |

---

## 8. 后续可扩展方向

- 接入 pytest，丰富用例类型（fixture / parametrize）
- 引入 Coverage，把“覆盖率低”也作为 RETRY 触发条件
- 增加第 3 个 Agent：**测试修复 Agent**，接收执行诊断后自动 Patch 测试文件（形成 生成 → 执行 → 修复 闭环）
- Workflow 持久化：把 state 落盘 JSON，支持断点续跑
- 可视化 Workflow 编排界面（DAG 编辑器 + 运行进度）
- 并行：对多个被测模块并行生成 + 并行执行
