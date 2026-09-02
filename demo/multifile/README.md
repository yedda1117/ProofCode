# Multi-file feedback demo

This demo is deliberately split across a parser and its integration caller.
Reset it before each recording:

```powershell
python demo/multifile/reset_demo.py
```

Confirm that the initial project fails:

```powershell
Push-Location demo/multifile/workspace
python -m unittest discover -v
Pop-Location
```

Run ProofCode from the repository root:

```powershell
python -m proofcode --workspace demo/multifile/workspace --max-steps 24 "修复 HTTP Bearer 鉴权，并保持职责分离：auth.py 的 extract_bearer_token 只接受格式严格且 token 非空的 Bearer 请求头，authenticate 只验证提取后的 token；middleware.py 必须组合这两个函数。不要修改测试。先检查实现和测试，并把关键发现、接口约束、当前假设和下一步写入证据关联的 working checkpoint。先修复解析器，运行 focused 验证 python -m unittest tests.test_auth -v；再运行项目策略要求的 python -m unittest discover -v。如果集成测试失败，把失败原因和下一步更新进 working checkpoint，再修复调用方；代码再次变化后重新运行完整验证。最后查看 diff，提出一条包含验证顺序和失败恢复步骤的 authentication SOP 长期记忆候选，并总结最终代码与当前 revision 的验证证据。"
```

The task demonstrates a causal sequence rather than isolated features:

1. Repository inspection builds the current working-memory anchor, then an
   evidence-linked plan records the dependent parser and caller obligations.
2. Editing `auth.py` advances the workspace revision.
3. The focused parser suite gives fast local feedback but cannot satisfy the
   completion gate by itself.
4. The project suite checks the `middleware.py` integration; any failure is fed
   back into the next model turn.
5. Editing the caller advances the revision again and invalidates the earlier
   validation, so the project suite must run on the final state.
6. Runtime accepts completion only after project-wide evidence from that final
   revision.
7. The authentication workflow is only staged during execution; after the
   completion gate succeeds, Runtime consolidates it as an auditable L3 SOP.

For the exact two-minute recording timeline and narration, see
[`VIDEO_SCRIPT.md`](VIDEO_SCRIPT.md).
