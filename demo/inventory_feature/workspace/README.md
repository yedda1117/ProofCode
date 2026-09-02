# Stockroom Inventory

一个仅使用 Python 标准库、HTML、CSS 和 JavaScript 的本地库存管理网站。

现有版本能够展示库存列表。待实现功能：CSV 导入必须先预览并校验 `sku,name,category,stock,reorder_level`，拒绝缺失字段、重复或已有 SKU、负数库存及非法阈值；整批合法才允许原子写入。网页还需显示缺货、低库存、正常统计与筛选。`scripts/audit_inventory.py` 应成为可重复执行的数据审计工具。测试是需求契约，不得修改。
