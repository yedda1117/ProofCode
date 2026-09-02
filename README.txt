ProofCode 项目说明

一、Git 仓库地址
https://github.com/yedda1117/ProofCode.git

二、如何运行
环境要求：Python 3.11 及以上、Git，以及支持原生工具调用的 OpenAI-compatible Chat Completions API。

在项目根目录执行：
python -m pip install -e .

PowerShell 中配置模型：
$env:MODEL_API_KEY="你的 API Key"
$env:MODEL_BASE_URL="服务地址（以 /v1 结尾）"
$env:MODEL_NAME="模型名称"

运行示例：
python -m proofcode --workspace ".\demo\workspace" "运行测试，定位并修复错误"

默认情况下，修改文件和执行命令前需要人工确认。仅在隔离且可信的工作区中使用 --approve-all。运行全部测试：
python -m unittest discover -v

三、特色功能
ProofCode 是受代码版本和执行证据约束的分层记忆 Agent。文件读取、修改、命令和测试形成 E 证据；工作区变化推进 revision，并保守地使旧认识和旧验证失效。当前任务的 Working Memory 保存有证据来源的目标、关键发现、风险与下一步，历史原文按需恢复。完成门控要求当前 revision 具备项目级验证，不能仅凭模型声明结束。跨任务记忆采用 L1 索引、L2 项目事实、L3 SOP/经验证的 Python Skill、L4 JSONL 原始轨迹；模型只提出候选，Runtime 在任务成功后复核证据、版本和安全规则再固化。

四、其它说明
记忆与轨迹位于工作区 .proofcode。Runtime 校验 provenance 与新鲜度，但不能证明自然语言结论必然被证据蕴含；项目级验证也不等于形式化正确。API Key 仅通过环境变量提供。

设计参考：GenericAgent（arxiv.org/abs/2604.17091）、CodePlan（arxiv.org/abs/2309.12499）、VRpilot（arxiv.org/abs/2405.15690）。
