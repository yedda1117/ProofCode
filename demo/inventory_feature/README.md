# 库存网站功能演示

## CMD：重置、启动与查看改造前页面

```cmd
set PROOFCODE_HOME=demo\inventory_feature\agent_memory
python demo\inventory_feature\reset_demo.py
cd /d C:\Users\ASUS\Documents\ChatGPT\agent-nku\demo\inventory_feature\workspace
python server.py
```

浏览器打开 `http://127.0.0.1:8765`。保留该服务器窗口，在新的 CMD 返回仓库根目录运行 Agent。

## 正式任务

继续使用上面设置的 `PROOFCODE_HOME`。项目事实和轨迹保存在 workspace；验证后的通用 SOP/Skill 保存在 Agent Home，可供其他 workspace 召回。

```cmd
python -m proofcode --workspace demo\inventory_feature\workspace --max-steps 48 "为现有 Stockroom 库存网站增加安全 CSV 批量导入和库存风险看板。导入前应预览并校验数据，任何一行有错都不能写入；页面应展示缺货、低库存和正常库存的统计、筛选及清晰反馈。同时完成项目中预留的库存审计脚本。保持现有数据兼容，不要修改测试。"
```

首次审批输入 `a`。模型等待可以加速，但保留 Working Memory、focused_only、revision 变化、失败反馈、完整验证、S/K 固化与绿色完成门控。

## 改造后页面演示

刷新浏览器，先选择 `samples/invalid.csv`，展示行级错误和按钮禁用；再选择 `samples/valid.csv`，预览并确认导入，展示统计卡片、风险标签和筛选更新。

## 第二次短运行：长期记忆按需召回

```cmd
python -m proofcode --workspace demo\inventory_feature\workspace --max-steps 10 "检查这个项目以后应如何安全导入库存数据。先根据长期 L1 索引读取相关 SOP 和 Skill，再读取 README 核对项目约束；不要修改文件，只总结可以复用的流程与审计工具。"
```
