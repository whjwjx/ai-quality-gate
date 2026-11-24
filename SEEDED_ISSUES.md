# 种子缺陷清单（Seeded Issues）

> 本文件记录靶子应用中**故意埋入**的缺陷。目的是练习"缺陷闭环"：
> 先让测试暴露它（红）→ 分析根因 → 修复 → 回归通过（绿）。
> 时间一长会分不清哪个洞是故意的，所以必须记录。

| ID | 位置 | 缺陷类型 | 对应测试 | 状态 |
|---|---|---|---|---|
| SEED-001 | `app/main.py` `get_document()` 等 3 个接口 | IDOR / BOLA（租户 A 可读取租户 B 文档） | `tests/test_api.py::test_tenant_isolation_idor`（参数化 3 个入口） | ✅ 已修复，见 `docs/defect-SEED-001-idor.md` |
| SEED-002 | `app/main.py` `parse_document()` | 命令注入（CWE-78，`shell=True` + 拼接文件名） | Semgrep 扫描 + `tests/test_api.py::test_parse_no_shell_injection` | 待暴露 |

## 修复顺序

1. ~~**SEED-001**：先写失败测试（期望跨租户返回 403），看到红；再在 `get_document()` 加 `if doc["tenant_id"] != x_tenant_id: raise HTTPException(403)`；回归跑绿。~~ **已完成（2026-11-24）**：抽 `_get_owned_document()` 统一校验，参数化覆盖 3 个入口，17 passed。详见 `docs/defect-SEED-001-idor.md`。
2. **SEED-002**：Semgrep 扫描报出后，把 `shell=True` 改为参数列表 `["file", filename]` 且 `shell=False`；补一条断言文件名带分号不会执行额外命令的测试。

## 设计要点

- SEED-001 防的是"同类问题重复发生"：任何按 ID 读取资源的接口都必须校验归属，补的测试应推广到所有 GET-by-id 接口。
- SEED-002 体现 Gate 角色：SAST 扫描在 PR 阶段阻断，而不是等运行时出事。
