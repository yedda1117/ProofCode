# ProofCode

ProofCode 是一个从零实现的轻量 Coding Agent。它直接调用 OpenAI-compatible Chat Completions API 的原生 tool calling 接口，不依赖 LangChain、LlamaIndex、OpenAI Agents SDK、Claude Agent SDK、AutoGen 或 CrewAI。

## 已实现

- 原生工具调用解析与多轮 Agent 循环
- 按完整工具交换保留和裁剪对话历史
- 工作区内的文件枚举、文本搜索和分段读取
- 唯一文本替换和安全的新文件创建
- 不经过 Shell 的本地进程执行
- 写文件和运行命令前的人工确认
- 工作区路径约束、命令超时和输出截断
- API 暂时错误的有限重试
- 最大步数和重复工具调用终止条件
- 修改文件后必须存在成功验证命令的完成门控

## 运行环境

- Python 3.11 或更新版本
- 支持原生 tool calling 的 OpenAI-compatible API

项目运行不依赖第三方 Python 包。

## 配置

PowerShell：

```powershell
$env:MODEL_API_KEY="your-api-key"
$env:MODEL_BASE_URL="https://your-provider.example/v1"
$env:MODEL_NAME="your-model-name"
```

`MODEL_BASE_URL` 应指向 API 的版本根路径。程序会请求：

```text
{MODEL_BASE_URL}/chat/completions
```

密钥只从环境变量读取，不应写进仓库。

## 使用

直接从仓库运行：

```powershell
python -m proofcode --workspace . "检查项目并修复失败的测试"
```

安装为命令：

```powershell
python -m pip install -e .
proofcode --workspace . "检查项目并修复失败的测试"
```

默认情况下，`replace_text`、`create_file` 和 `run_command` 每次执行前都会请求确认。仅在隔离且可信的工作区中使用自动批准：

```powershell
python -m proofcode --workspace . --approve-all "运行测试并修复错误"
```

## 测试

```powershell
python -m unittest discover -v
```

测试使用脚本化假模型验证完整流程，不需要 API key，也不会产生模型费用。

## 设计边界

ProofCode 的命令工具使用 `subprocess.run(..., shell=False)`，拒绝直接启动 Shell 解释器，并限制工作目录和超时时间。这些措施用于减少误操作，但不是恶意代码沙箱。目标仓库及其测试代码不可信时，应在容器或虚拟机中运行整个进程。

第一版只支持 UTF-8 文本文件。编辑采用唯一文本替换：待替换内容出现零次或多次都会拒绝写入。这比整文件覆盖更保守，也便于模型根据错误重新读取准确上下文。

## 参考设计

- [mini-SWE-agent](https://github.com/SWE-agent/mini-swe-agent)：小型、线性的 Agent Harness
- [mini-coding-agent](https://github.com/rasbt/mini-coding-agent)：可阅读的本地 Coding Agent 实现
- [SWE-agent](https://arxiv.org/abs/2405.15793)：面向模型的工具接口设计
- [Agentless](https://arxiv.org/abs/2407.01489)：定位、修复和验证的阶段化思路

ProofCode 没有复制这些项目的 Agent 实现，参考的是最小循环、工具边界和验证优先的设计原则。
