# ai-quality-gate

一个质量与安全门禁实践项目：亲手搭建一条"每个门禁都让它失败过一次"的质量/安全门禁链路。覆盖测试自动化、CI 卡点、AI 评测与供应链安全的完整实践。

## 阶段进度

- [x] 阶段 1：pytest 场景化 + CI 门禁 + 缺陷闭环（骨架已就绪）
- [ ] 阶段 2：评测集 + 准确率回归 + 注入用例
- [ ] 阶段 3：Gitleaks / Semgrep / Trivy 阻断
- [ ] 阶段 4：Cosign + 准入验证 + 小工具
- [ ] 阶段 5：Issues 闭环 + 告警

## 靶子应用

最小 FastAPI 文档抽取服务，5 个接口 + 1 个冒烟页面。故意埋了 2 颗种子缺陷，见 `SEEDED_ISSUES.md`。**不要用于生产。**

## 本地开发

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m pytest tests/ -v
```

E2E 测试本地自动使用系统 Chrome（`channel="chrome"`），CI 里自动使用 Playwright Chromium，两边互不干扰。

## 文档

- `SEEDED_ISSUES.md` — 种子缺陷与修复顺序

> 个人笔记不随仓库公开。
