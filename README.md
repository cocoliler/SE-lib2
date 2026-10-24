# Test Workflow Agent

一个面向 Python 项目的 **测试流程 Agent Workflow**。按顺序协调两个 Agent：**测试生成 Agent** 与 **测试执行 Agent**，在 Workflow 编排器控制下完成：

```
代码 → 生成测试 → 执行 → 诊断 → [可选] 重新生成
```

对应 Homework 2 的「测试流程」方向：

| 方向 | 流程描述 | Agent 组成 |
|---|---|---|
| 测试流程 | 代码 → 生成测试 → 执行 | 测试生成Agent + 测试执行Agent |

## 1. 功能概览

- 读取 Python 文件或目录，基于 AST 提取函数签名 / 参数 / docstring
- 调用 LLM 生成可直接运行的 `unittest` 风格测试
- 自动运行测试，解析每个用例的 PASS / FAIL 和错误信息
- 失败时调用 LLM 做执行诊断：判断是代码 Bug 还是测试构造问题，给出修复建议
- **条件分支**：执行后由 Orchestrator（可启发式 / 可 LLM）决定 FINISH 或 RETRY
- **重试 / 循环**：对“完全无法执行（语法 / 导入错）”的生成结果，最多重试 N 次
- 共享状态（WorkflowState）+ 结构化 Agent 消息（AgentMessage），实现 Agent 协作与状态追踪
- 完整日志、步骤耗时、状态枚举，便于回放和审计

## 2. 技术栈

- Python 3.10+
- OpenAI-compatible Python SDK（`openai>=1.40`）
- Python 标准库：`ast` / `unittest` / `subprocess` / `dataclasses`
- 不依赖大型 Agent 框架，直接实现 Workflow 与 Agent Loop，便于教学与原理展示

## 3. 项目结构

```text
se-lib2/
├── app.py                    # CLI 入口：run / analyze / exec-test
├── agent/
│   ├── __init__.py
│   ├── schemas.py            # 数据结构：WorkflowState / AgentMessage / 测试结果等
│   ├── llm.py                # LLM 客户端 + 指数退避重试
│   ├── prompts.py            # 各 Agent / Orchestrator 的 Prompt 模板
│   ├── test_generator.py     # 测试生成 Agent
│   ├── test_executor.py      # 测试执行 Agent
│   └── workflow.py           # Workflow 编排器 + 最终报告
├── tools/
│   ├── __init__.py
│   ├── file_tool.py          # 文件读取 / 写测试文件
│   ├── code_tool.py          # Python AST 分析（提取函数签名）
│   └── test_tool.py          # 测试执行 + stdout/stderr 解析
├── examples/
│   └── sample_module.py      # 示例代码：含正确函数 + 故意带 Bug 的 broken_max
├── tests/
│   └── test_tools.py         # 工具层单元测试（不依赖 LLM API）
├── requirements.txt
├── .env.example
├── .gitignore
├── Design.md
└── README.md
```

## 4. 安装

建议 Python 3.10+：

```bash
python3 -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 5. 配置 LLM

复制环境变量模板：

```bash
cp .env.example .env
```

然后填写：

```text
LLM_API_KEY=你的API_KEY
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=你的模型名（如 gpt-4o-mini）
```

## 6. 使用方法

### 6.1 运行完整 Workflow（主流程）

对示例代码执行「生成测试 → 执行 → 诊断 → 可选重试」：

```bash
python app.py run examples/sample_module.py
```

输出主要分为：
- 实时进度日志（每一步开始/结束、Orchestrator 决策）
- 最终报告：Workflow 摘要、测试文件路径、设计说明、执行结果、LLM 诊断

常用参数：

```bash
# 自定义生成要求
python app.py run examples/sample_module.py -r "重点测试 broken_max 与 divide 的边界情况"

# 增加生成重试次数（默认 1 次）
python app.py run examples/sample_module.py --max-retries 2

# 不用 LLM 做 Orchestrator 决策，只用启发式规则
python app.py run examples/sample_module.py --no-llm-orchestrator

# 指定测试文件输出目录
python app.py run examples/sample_module.py --output-dir ./my_tests
```

### 6.2 只看函数签名分析（不调用 LLM）

```bash
python app.py analyze examples/
```

用于快速验证 AST 工具是否能正确解析函数。

### 6.3 只执行某个已生成的测试文件

```bash
python app.py exec-test examples/tests_generated/test_sample_module.py examples/
```

### 6.4 运行工具层自带单元测试（不依赖 LLM）

```bash
python -m unittest discover -s tests -v
```

## 7. 核心概念速览

### WorkflowState

所有 Agent 共享的状态对象，包含：

- 步骤 `steps`（每个步骤的输入/输出/错误/重试次数/耗时）
- 消息 `messages`（Agent 之间的结构化事件）
- 数据产物：`source_files / code_analyses / generated_tests / execution_results`
- 运行日志 `logs`

### Agent 间通信

示例：

```
TEST_GENERATOR -> TEST_EXECUTOR  [generated_tests_ready]
  payload: { test_file, target_functions, reasoning }

TEST_EXECUTOR -> ORCHESTRATOR    [execution_done]
  payload: { total, passed, failed, exit_code, has_runtime_error }

ORCHESTRATOR  -> ALL             [workflow_decision]
  payload: { decision: RETRY/FINISH, reason, retry_count }
```

### 条件分支与循环

Orchestrator 在执行后判定：

- 全部通过 → FINISH（SUCCESS）
- 完全不能执行（语法/导入错 / 0 用例）且重试次数未满 → RETRY（回到生成阶段）
- 否则 → FINISH（PARTIAL 或 FAILED，取决于是否存在有效执行）


## 8. 已知限制

- 当前主要面向单模块或小批量模块的 unittest 生成，暂未集成 pytest / coverage。
- LLM 调用失败会报错重试，连续失败会抛出异常，需要用户检查 API Key 与网络。
- 沙箱隔离：测试执行在当前 Python 解释器的 subprocess 中运行，请勿对不可信的第三方代码直接使用。
