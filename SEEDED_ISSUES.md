# 种子缺陷清单（Seeded Issues）

> 本文件记录靶子应用中**故意埋入**的缺陷。目的是练习"缺陷闭环"：
> 先让测试暴露它（红）→ 分析根因 → 修复 → 回归通过（绿）。
> 时间一长会分不清哪个洞是故意的，所以必须记录。

| ID | 位置 | 缺陷类型 | 对应测试 | 状态 |
|---|---|---|---|---|
| SEED-001 | `app/main.py` `get_document()` 等 3 个接口 | IDOR / BOLA（租户 A 可读取租户 B 文档） | `tests/test_api.py::test_tenant_isolation_idor`（参数化 3 个入口） | ✅ 已修复，见 `docs/defect-SEED-001-idor.md` |
| SEED-002 | `app/main.py` `parse_document()` | 命令注入（CWE-78，`shell=True` + 拼接文件名） | `tests/test_api.py::test_parse_does_not_use_shell`（断言调用契约） | ✅ 已修复，见 `docs/defect-SEED-002-cmdi.md` |

## 修复顺序

1. ~~**SEED-001**：先写失败测试（期望跨租户返回 403），看到红；再在 `get_document()` 加 `if doc["tenant_id"] != x_tenant_id: raise HTTPException(403)`；回归跑绿。~~ **已完成（2026-11-24）**：抽 `_get_owned_document()` 统一校验，参数化覆盖 3 个入口，17 passed。详见 `docs/defect-SEED-001-idor.md`。
2. ~~**SEED-002**：Semgrep 扫描报出后，把 `shell=True` 改为参数列表 `["file", filename]` 且 `shell=False`；补一条断言文件名带分号不会执行额外命令的测试。~~ **已完成（2026-11-24）**：`sast-scan` 门禁报红 → 加契约测试（先红）→ 改参数列表 + `shell=False` → 18 passed、semgrep 退出码 0。详见 `docs/defect-SEED-002-cmdi.md`。

## 设计要点

- SEED-001 防的是"同类问题重复发生"：任何按 ID 读取资源的接口都必须校验归属，补的测试应推广到所有 GET-by-id 接口。
- SEED-002 体现 Gate 角色：SAST 扫描在 PR 阶段阻断，而不是等运行时出事。

## SEED-002 的一个额外教训：测试假绿

第一版测试是"上传带 `; echo MARKER` 的文件名 → 断言输出里没有 MARKER"。它在本地**通过**了，但原因是：

1. Windows 没有 `file` 命令，`shell=True` 执行失败
2. 输出是 GBK，`text=True` 按 UTF-8 解码抛异常
3. 捕获到的 stdout 为空 → "MARKER 不在输出里" 恰好成立

改成断言**调用契约**（`shell is False` 且命令是参数列表）后才真正变红。结论：
**靠"输出里没有某个字符串"判断注入是否被防住，容易被编码和环境差异骗过；断言调用形态更可靠。**
