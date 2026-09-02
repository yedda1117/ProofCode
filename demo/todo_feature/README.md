# Todo 功能生成演示

这个演示从一个已经可运行的 JSON Todo CLI 开始。Agent 的任务不是修复一行故障，而是跨数据模型、持久化、业务服务和 CLI 完成一项新功能。

## 1. 重置并展示改造前应用

在 ProofCode 仓库根目录执行：

```powershell
python demo/todo_feature/reset_demo.py
Push-Location demo/todo_feature/workspace
python -m todo_app.cli --data demo_todos.json list
Pop-Location
```

此时能看到已有 Todo 数据，但没有优先级，也没有 `stats` 命令。

## 2. 运行一个真实编程任务

```powershell
python -m proofcode --workspace demo/todo_feature/workspace --max-steps 40 "为现有待办事项管理程序完整实现优先级和统计功能。要求：Todo 新增 priority，只允许 low、medium、high，默认 medium，并兼容旧 JSON；add 支持 --priority；list 按未完成优先、同组内 high、medium、low 排序；新增 stats 命令，输出总数、完成数和各优先级数量；完成 scripts/check_legacy.py，使它能检查旧 JSON 是否可由当前程序兼容读取。不要修改测试。先读取 README、实现和测试，把跨文件约束与下一步写入有 E 证据的 working checkpoint。先完成 model/storage 并运行 python -m unittest tests.test_models_storage -v；再完成 service、CLI 和兼容检查脚本。重要阶段变化后刷新 working checkpoint。最后运行项目策略要求的 python -m unittest discover -v；验证通过后只调用一次不带 path 的 show_diff，同时提出 JSON schema 演化 SOP 和 scripts/check_legacy.py Python Skill 两个长期记忆候选，然后立即总结实现和当前 revision 的验证证据。"
```

第一次黄色审批面板输入 `a`，只对本次运行自动批准后续修改和命令。

## 3. 展示生成后的功能

Agent 完成后执行：

```powershell
Push-Location demo/todo_feature/workspace
python -m todo_app.cli --data demo_todos.json add "提交申请材料" --priority high
python -m todo_app.cli --data demo_todos.json add "整理读书笔记" --priority low
python -m todo_app.cli --data demo_todos.json list
python -m todo_app.cli --data demo_todos.json stats
Pop-Location
```

对比重点：改造前只有无优先级列表；改造后有排序后的 `HIGH/MEDIUM/LOW` 列表和统计摘要。

## 视频中保留的核心状态

1. 改造前 CLI 的实际输出；
2. Agent 读取四层代码并更新 Working Memory；
3. 黄色人工确认；
4. model/storage focused test 通过，但显示 `focused_only`；
5. 后续代码修改推进 revision，使旧验证 stale；
6. 完整测试在最终 revision 通过；
7. `长期记忆已固化 · S...`；
8. 绿色 Completion Gate；
9. 改造后 `list` 和 `stats` 的实际输出。

## 4. 用第二次短任务展示按需召回

主任务结束后，运行：

```powershell
python -m proofcode --workspace demo/todo_feature/workspace --max-steps 8 "检查这个项目以后应如何安全修改 Todo JSON schema。先查看长期 L1 索引，读取相关 SOP 和 Skill；再读取 README 核对当前项目，最后只总结已有经验，不修改文件。"
```

这一段不属于第二个编程任务，只用约十秒展示：新 Agent 启动后只看到 L1 的 `S.../K...` 指针，再通过 `read_memory` 按需恢复 SOP 和可执行 Skill，而不是把长期记忆全文始终塞入上下文。

模型等待可以加速，以上状态不要剪掉。若模型修改了测试、没有形成 Working Memory 或没有提出 SOP，则 reset 后重新录制；Runtime 中没有硬编码这条演示路线。
