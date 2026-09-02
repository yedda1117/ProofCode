# Todo CLI

这是一个使用 JSON 文件持久化的命令行待办事项应用。

现有命令：

```text
todo add TITLE
todo list
todo done ID
```

待实现需求：为任务增加 `low / medium / high` 优先级并兼容缺少该字段的旧 JSON；列表应先显示未完成事项，再按优先级排序；CLI 应支持设置优先级并提供任务统计摘要。`scripts/check_legacy.py` 应成为可以重复执行的旧数据兼容检查工具。测试是需求契约，不应修改。
