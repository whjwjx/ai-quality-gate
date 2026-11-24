# 缺陷分析报告 · SEED-001 跨租户越权（IDOR/BOLA）

## 1. 缺陷摘要

| 项 | 内容 |
|---|---|
| 编号 | SEED-001 |
| 类型 | IDOR / BOLA（不安全的直接对象引用 / 对象级授权失效） |
| 严重级别 | 高（数据泄露，且认证完全合法，传统登录拦截防不住） |
| 发现方式 | 参数化越权测试 |
| 状态 | 已修复 |

## 2. 影响面

不是单个接口的问题。排查全部按 `doc_id` 访问资源的入口后，发现 **3 处**同样缺失归属校验：

| 接口 | 后果 |
|---|---|
| `GET /api/v1/documents/{doc_id}` | 跨租户读取文档元数据 |
| `POST /api/v1/extract?doc_id=` | 跨租户触发字段抽取，间接拿到内容 |
| `POST /api/v1/documents/{doc_id}/parse` | 跨租户触发解析，且叠加命令注入风险 |

攻击路径：租户 A 正常上传拿到 `doc_id` → 租户 B 带自己的租户头请求同一 ID → 返回 200，读到 A 的数据。

## 3. 根因

三个接口都写成了：

```python
doc = _TENANT_DOCS.get(doc_id)      # 只判断存在性
if doc is None:
    raise HTTPException(404)
# 缺少：if doc["tenant_id"] != x_tenant_id: raise 403
```

**直接原因是漏了归属校验；根本原因是"按 ID 取资源"这个动作没有统一的入口约束**——每个接口各写一遍，漏一处就是一个洞。

## 4. 修复

不是补一行，而是抽公共函数 `_get_owned_document(doc_id, tenant_id)`，三个接口统一走它：

```python
def _get_owned_document(doc_id: str, tenant_id: str) -> dict:
    doc = _TENANT_DOCS.get(doc_id)
    if doc is None:
        raise HTTPException(404, "document not found")
    if doc["tenant_id"] != tenant_id:
        raise HTTPException(403, "forbidden: resource belongs to another tenant")
    return doc
```

选择 403 而不是 404：明确区分"不存在"和"无权限"，便于审计和排查；代价是暴露了资源存在性，高敏感场景可改为统一返回 404。

## 5. 防复发

| 措施 | 说明 |
|---|---|
| 测试参数化覆盖 3 个入口 | 不只测一个接口，任何新增的 doc_id 接口都要加进参数列表 |
| 新增回归保护用例 | `test_owner_can_still_access` 确认修复没误伤正常访问 |
| 代码层收口 | 新接口必须走 `_get_owned_document`，绕过即代码评审不通过 |

**这个测试防的是哪类重复问题**：任何"用用户可控 ID 取资源"的接口，如果没有统一归属校验，就会重复出现同类越权。测试的参数化结构让"漏一个接口"直接暴露。

## 6. 证据链

| 阶段 | 结果 |
|---|---|
| 暴露缺陷 | 去掉 `xfail` 后本地 `assert 200 == 403` 失败 |
| 修复后回归 | 17 passed（含 3 条越权用例 + 1 条越权回归保护） |
| 门禁验证 | 该修复随 PR 通过 `quality-gate` 检查后才允许合并 |
