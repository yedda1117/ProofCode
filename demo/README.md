# Two-minute demo

The demo workspace contains one intentional bug: `authenticate("")` returns
`True`. Reset it before every take:

```powershell
python demo/reset_demo.py
```

Run ProofCode from the repository root without `--approve-all`, so write and
command confirmations remain visible:

```powershell
python -m proofcode --workspace demo/workspace --max-steps 16 "修复 auth.py：空 token 必须被拒绝，非空 token 仍应通过。请先检查实现和测试；修改后先运行单个用例 python -m unittest tests.test_auth.AuthTests.test_empty_token_is_rejected；随后调用 list_context 展示常驻工作锚点，用 search_context 搜索该测试名称并定位验证证据，再用返回的 E 编号和 offset 调用 read_context 恢复原文；最后运行项目级基线 python -m unittest discover -v，再总结修改和验证。"
```

Expected visible sequence:

1. `read_file` inspects the implementation and test.
2. `replace_text` pauses at the yellow `需要人工确认` panel; answer `a` to
   approve this action and automatically allow the remaining actions in this run.
3. The focused test then runs automatically and passes.
4. `list_context` shows the always-on workspace anchor and
   `validation_status: focused_only` without injecting all raw output.
5. `search_context` locates the focused-test evidence; `read_context` then
   recovers the requested section from its `E...` record.
6. The project-wide discovery command requires approval and passes; the green
   `任务完成 · 已满足执行证据门控` heading confirms that Runtime accepted
   evidence from the current revision.

The exact number of model steps and evidence IDs can vary. Record one complete
run first, then trim model latency rather than cutting any approval, context, or
validation transition.
