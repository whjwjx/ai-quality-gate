# ai-quality-gate

一个质量与安全门禁实践项目：亲手搭建一条"**每个门禁都让它失败过一次**"的门禁链路。
覆盖测试自动化、AI 输出评测、静态/依赖/镜像扫描、镜像签名与准入、以及发现闭环。

## 已知边界（先读这一节）

**下面这些不是 bug，是刻意的取舍。** 接手前请先读，否则可能把设计当成缺陷去"修"。

| 边界 | 原因 | 想改的话 |
|---|---|---|
| **Pager 只覆盖 CI 失败** | 没有线上流量，无运行时监控 | 要监控得先有线上部署 |
| **评测集只有 15 条** | 5 类文档 × 5 种注入，够验证机制，不够做统计 | 扩到 100+ 才有置信度 |
| **E2E 只有 2 条** | 浏览器测试慢且脆，主要靠 API 层覆盖 | 增加会显著拉长 CI |
| **镜像 CVE 靠 `apt-get upgrade`** | 临时补底座，不是长期方案 | 生产应定期重建 base image |
| **私钥存在 GitHub Secrets** | 演示用长期密钥对 | 生产用 KMS/HSM 或 keyless |
| **准入例外靠 label，无审批流** | 单人项目没有审批环节 | 生产要接 PR 审批或 PolicyException |
| **`docker build` 必须带 `--provenance=false`** | 否则镜像变 manifest list，签名 digest 与准入解析的 digest 不一致 | **不要删这个参数**，删了签名会"莫名其妙失败" |
| **签名必须上传 tlog** | 准入控制器会校验透明日志条目 | **不要加 `--tlog-upload=false`**，加了已签名镜像也会被拒 |
| **`学习路线.md` / `学习笔记.md` 不进仓库** | 个人笔记，已在 `.gitignore` | 不要"顺手"提交 |

## 门禁全景

7 个 required check，dev / main 都开启 `enforce_admins`。

| Job | 工具 | 阻断条件 |
|---|---|---|
| `quality-gate` | pytest（52 条单测 + E2E） | 任一失败 |
| `eval-gate` | 快照回放 + 判定 | 准确率 < 90%/70%，或安全类 < 100% |
| `secret-scan` | Gitleaks | 任何凭证泄露 |
| `sast-scan` | Semgrep（自研 3 条规则） | ERROR 级发现 |
| `sca-scan` | Trivy + SBOM | HIGH/CRITICAL 且有修复版本 |
| `image-pipeline` | Docker + Cosign | 镜像扫描失败 / 签名失败 |
| `admission-verify` | kind + Kyverno | 签名策略未生效 |

非门禁（副作用类）：

- `issue-sync` — 扫描失败时建 Issue（幂等去重）
- `exception-audit` — 定时检查 `exception:expire-*` 是否到期
- `notify-on-failure` — dev/main 失败时推飞书（PR 失败静默）

## 靶子应用

最小 FastAPI 文档抽取服务，5 个接口 + 1 个冒烟页面。
故意埋了 2 颗种子缺陷，均已修复并留下报告，见 `SEEDED_ISSUES.md`。**不要用于生产。**

## 本地开发

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m pytest tests/ -v --ignore=tests/test_e2e.py   # 单测
bash scripts/test_e2e.sh                                                   # E2E
python -m scripts.run_eval --prompt-version v1 --report reports/eval-report.md
docker build --provenance=false -t docextract:local .                      # 注意参数
```

E2E 本地自动使用系统 Chrome（`channel="chrome"`），CI 里自动使用 Playwright Chromium。

## 文档索引

| 文件 | 内容 |
|---|---|
| `docs/defect-SEED-001-idor.md` | 越权缺陷分析（根因、修复、防复发） |
| `docs/defect-SEED-002-cmdi.md` | 命令注入缺陷分析 + "测试假绿"事故复盘 |
| `docs/security-findings.md` | 扫描发现判断表（真风险/误报/可接受）+ 两次假绿 |
| `docs/supply-chain.md` | 供应链四层结构、红绿证据、8 个坑、生产差距 |
| `docs/issue-loop.md` | Gate/Pager/Memory 分工、幂等设计、飞书签名坑 |
| `SEEDED_ISSUES.md` | 种子缺陷台账 |

> 个人笔记不随仓库公开。
