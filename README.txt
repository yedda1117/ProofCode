ProofCode

一、Git 仓库地址
https://github.com/yedda1117/ProofCode.git

二、运行方法
要求 Python 3.11+、Git 和支持 tool calling 的兼容 API。
安装：python -m pip install -e .
设置三个 MODEL 环境变量后运行：
python -m proofcode --workspace ".\demo\workspace" "运行测试并修复错误"
测试：python -m unittest discover -v

三、特色功能
1. 自研 Agent Runtime
不使用 Agent 框架，自行实现模型请求、工具解析、上下文、错误处理和循环终止。

2. 受控本地工具
支持文件浏览、搜索、编辑、补丁、Git 差异和本地命令；限制路径、超时和输出，危险操作需批准。

3. 版本化证据门控
读写与执行形成 E 证据；文件变化推进 revision，旧认识与验证失效。当前版本未通过项目级验证时拒绝完成。

4. 证据关联的 Working Memory
维护目标、发现、约束和下一步并绑定证据；依赖变化后自动 stale，历史原文通过 C/E 指针恢复。

5. L1-L4 分层记忆
L1 合并项目与全局索引，L2 保存项目事实，L3 保存可迁移 SOP/Skill，L4 保存 JSONL 会话；内容按需读取。

6. 验证驱动的 Skill 演化
Agent 从真实任务的成功路径提炼 Python Skill 并绑定 provenance；门控通过后，Runtime 复核证据、代码和版本，再固化到全局 L3，供后续项目召回执行。

7. Memory Management SOP
模型只提出记忆候选；Runtime 在成功后检查证据、项目验证和敏感信息，再写入项目或全局记忆。

8. 执行反馈与审计
测试、构建和静态检查驱动修复；重复检测促使 Agent 复用证据。轨迹记录调用、验证与停止原因。

四、参考与边界
参考 GenericAgent、CodePlan 与 VRpilot。Runtime 验证执行证据和版本，但不形式化证明需求正确；ProofCode 也不是恶意代码沙箱。
