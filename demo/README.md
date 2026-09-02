# Two-minute demo

The demo workspace contains one intentional bug: `authenticate("")` returns
`True`. Reset it before every take:

```powershell
python demo/reset_demo.py
```

Run ProofCode from the repository root without `--approve-all`, so write and
command confirmations remain visible:

```powershell
python -m proofcode --workspace demo/workspace --max-steps 16 "修复 auth.py：空 token 必须被拒绝，非空 token 仍应通过。请先检查实现和测试；修改后先运行单个用例 python -m unittest tests.test_auth.AuthTests.test_empty_token_is_rejected；随后调用 list_context 展示 L1/L2，并根据索引用 read_context 读取该验证对应的 L3 原始证据；最后运行项目级基线 python -m unittest discover -v，再总结修改和验证。"
```

Expected visible sequence:

1. `read_file` inspects the implementation and test.
2. `replace_text` pauses at the yellow `需要人工确认` panel; answer `a` to
   approve this action and automatically allow the remaining actions in this run.
3. The focused test then runs automatically and passes.
4. `list_context` shows the workspace revision, changed file, L1 index, L2
   summaries, and `validation_status: focused_only`.
5. `read_context` recovers the complete focused-test output from its `E...`
   evidence record.
6. The project-wide discovery command requires approval and passes; the green
   `任务完成 · 已满足执行证据门控` heading confirms that Runtime accepted
   evidence from the current revision.

The exact number of model steps and evidence IDs can vary. Record one complete
run first, then trim model latency rather than cutting any approval, context, or
validation transition.
