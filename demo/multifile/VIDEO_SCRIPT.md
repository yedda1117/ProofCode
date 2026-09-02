# 两分钟演示脚本

## 录制前

在仓库根目录执行：

```powershell
chcp 65001
$env:PYTHONUTF8="1"
python demo/multifile/reset_demo.py
```

先确认模型环境变量已经配置。正式录制只运行下面一个真实任务：

```powershell
python -m proofcode --workspace demo/multifile/workspace --max-steps 24 "修复 HTTP Bearer 鉴权，并保持职责分离：auth.py 的 extract_bearer_token 只接受格式严格且 token 非空的 Bearer 请求头，authenticate 只验证提取后的 token；middleware.py 必须组合这两个函数。不要修改测试。先检查实现和测试，并把关键发现、接口约束、当前假设和下一步写入证据关联的 working checkpoint。先修复解析器，运行 focused 验证 python -m unittest tests.test_auth -v；再运行项目策略要求的 python -m unittest discover -v。如果集成测试失败，把失败原因和下一步更新进 working checkpoint，再修复调用方；代码再次变化后重新运行完整验证。最后查看 diff，提出一条包含验证顺序和失败恢复步骤的 authentication SOP 长期记忆候选，并总结最终代码与当前 revision 的验证证据。"
```

第一次出现审批时输入 `a`，表示仅对本次运行自动批准后续写操作和命令。不要使用 `--approve-all`，否则视频看不到人机权限边界。

## 时间线与解说

### 0:00—0:15　问题与设计

画面保持在启动横幅和任务文本。

> 这是我独立实现的编程智能体 ProofCode。编程任务有两个特殊问题：关键信息散落在长代码与执行轨迹中，而且测试结果只对产生它的代码版本有效。因此系统主线不是简单堆工具，而是分层记忆、版本化执行证据和完成门控。

### 0:15—0:35　读取与 Working Memory

保留读取 `auth.py`、`middleware.py`、测试以及“更新工作检查点”的画面。

> 模型负责发现解析器和调用方的职责关系；Runtime 为每次读取生成 E 证据。Working Memory 保存关键发现、接口约束、假设和下一步，每条认识必须引用真实证据，不能只是无来源的模型摘要。

### 0:35—0:52　人工确认与第一次修改

在黄色确认框停留一秒，输入 `a`。保留 `workspace r1`。

> 写文件和执行命令默认需要确认。第一次修改推进 workspace revision；依赖旧代码的认识和验证会失效。本次输入 a 只授权当前运行，不改变 Agent 的正常执行逻辑。

### 0:52—1:10　局部测试通过但不能结束

保留 `tests.test_auth` 通过以及 `focused_only` 状态。

> Agent 先运行解析器的局部测试获得快速反馈。但 Runtime 将它识别为 focused validation，不能用一个局部甚至无关测试冒充整个任务已经完成。

### 1:10—1:32　真实失败反馈与跨文件修复

保留完整测试中 middleware 失败、Working Memory 更新、修改 `middleware.py` 和 revision 再次推进的画面。模型等待部分可加速。

> 项目级测试暴露调用方仍把原始请求头直接传给认证函数。失败输出返回下一轮，Agent 更新有证据的工作假设并修复第二个文件。代码到达新 revision 后，前一次测试证据再次 stale，必须重新验证最终状态。

### 1:32—1:50　完成门控与经验固化

保留完整 8 项测试通过、`show_diff`、长期记忆候选和“长期记忆已固化”。

> 最终只有项目策略指定的完整测试在当前 revision 通过，Completion Gate 才接受结束。认证修复流程先是候选，任务成功后 Runtime 才复核证据并固化为 L3 SOP；未来任务只常驻 L1 指针，正文按需读取。

### 1:50—2:00　边界

保留最终绿色完成标题。

> 这个门控不是正确性证明，它保证的是：Agent 不能完全依赖自然语言宣布完成，必须提供当前代码版本真实执行得到的证据。完整轨迹则保存在 L4 JSONL 中供审计。

## 必须保留的画面

剪辑时可以加速模型等待，但不要剪掉以下状态：

1. `更新工作检查点`，且画面中出现 `E...` 证据引用；
2. 黄色人工确认面板；
3. 第一次修改后的 `工作区 r1`；
4. focused test 通过后的 `验证 focused_only`；
5. middleware 集成测试真实失败；
6. 第二次修改后 revision 再次变化；
7. 最终 8 个测试通过及 `验证 passed`；
8. `长期记忆已固化 · S...`；
9. `任务完成 · 已满足执行证据门控`。

如果模型没有提出 SOP，或者直接同时修改两个文件导致没有出现中间集成失败，这一条素材不要使用；重新 reset 后录制。演示依赖真实模型决策，不在 Runtime 中硬编码演示路径。
