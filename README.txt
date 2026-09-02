ProofCode

一、Git 仓库地址
https://github.com/yedda1117/ProofCode.git

二、运行方法
安装：python -m pip install -e .
配置三个 MODEL 环境变量后运行：
python -m proofcode --workspace ".\demo\workspace" "运行测试并修复错误"
测试：python -m unittest discover -v

三、特色功能
1. 基础 Coding Agent
支持文件编辑、本地命令、Git 差异、人工审批和 JSONL 轨迹。

2. GenericAgent 的 L1-L4 分层记忆
L1 为索引，L2 为事实，L3 为 Coding SOP/Python Skill，L4 为轨迹，内容按需读取。

3. Memory Management SOP
模型只提出候选；成功后 Runtime 检查证据、版本、项目验证与敏感信息再写入。

4. Coding SOP 与 Python Skill
SOP 保存已验证流程；Skill 只能复制工作区内的 Python 文件，不能由参数直接生成。

5. CodePlan 的跨文件依赖思想
Working Memory 记录目标、发现和下一步，并绑定证据；依赖文件变化后自动 stale。

6. VRpilot 的执行反馈机制
测试、构建和命令结果返回 Agent，失败结果驱动下一轮修复。

7. ProofCode 的版本化证据约束
文件变化推进 revision，旧认识与验证失效。completion gate 要求当前版本具有项目级验证。

8. SOP/Skill 的跨任务复用流水线
检查代码 → 产生证据 → 更新 Working Memory → 修改文件 → revision 推进 → 测试修复 → completion gate → 保存 SOP/Skill → 下一任务从 L1 按需读取。

四、参考与边界
GenericAgent（arXiv:2604.17091）及其 Memory Management SOP；CodePlan（arXiv:2309.12499）；VRpilot（arXiv:2405.15690）。Runtime 检查证据与版本，但不证明模型结论正确。
