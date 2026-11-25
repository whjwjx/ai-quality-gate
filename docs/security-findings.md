# 安全扫描发现判断表

> 阶段三要求：每一条扫描发现都要给出判断——**真风险 / 误报 / 可接受风险**，附理由与 OWASP 类别。
> 只报"扫出几条"没有意义，判断才是产出。

## 一、当前门禁配置

| Job | 工具 | 阻断条件 | 特点 |
|---|---|---|---|
| `secret-scan` | Gitleaks | **任何发现都阻断** | 密钥泄露零容忍 |
| `sast-scan` | Semgrep（自研规则） | ERROR 级别发现 | 规则可控，无 registry 噪音 |
| `sca-scan` | Trivy | HIGH / CRITICAL **且有修复版本** | 排除 unfixed，避免门禁卡死 |

三者都是 `dev` / `main` 的 required check，`enforce_admins: true`。

## 二、发现与判断

### 1. `subprocess.run(..., shell=True)` — 真风险，已修复

| 项 | 内容 |
|---|---|
| 位置 | `app/main.py` `parse_document()` |
| 规则 | `python-subprocess-shell-true` |
| 类别 | CWE-78 / OWASP A03:2021 Injection |
| 判断 | **真风险** |
| 理由 | 文件名来自上传接口，未过滤 shell 元字符。`; && \| $()` 可直接执行任意命令 |
| 处置 | 改为 `["file", filename]` + `shell=False`，补契约测试 |

### 2. `ghp_0123456789...` — 测试样本，精确豁免

| 项 | 内容 |
|---|---|
| 位置 | `tests/security/fixtures/fake_github_token.txt` |
| 规则 | `github-pat` |
| 判断 | **误报**（人工构造的占位值） |
| 理由 | 值公开、不对应任何账号、无法调用 API。格式刻意模仿真实 token 的形态 |
| 处置 | 加 allowlist，且**只豁免这个确切值**而不是整个目录——否则以后有人往该目录塞真密钥就扫不到了 |

### 3. `certifi==2022.12.7` — 实验样本，已移除

| 项 | 内容 |
|---|---|
| 漏洞 | GHSA-6q48-6c7w-9gw2（CRITICAL）、CVE-2023-37920（HIGH）、CVE-2024-39689（LOW） |
| 类别 | OWASP A06:2021 Vulnerable and Outdated Components |
| 判断 | **真风险**（仅存在于红绿实验期间） |
| 理由 | 证书校验实现缺陷可能导致 TLS 验证被绕过 |
| 处置 | 已回退到 `httpx` 解析出的安全版本 |

### 4. `eval/exec` 与 `yaml.load` 规则 — 当前无命中

| 项 | 内容 |
|---|---|
| 判断 | **规则就绪，代码无命中** |
| 说明 | 两条规则已启用但当前代码没有触发。它们是为"以后有人加进来"准备的，不是无效规则 |

## 三、两次"假绿"事故（比发现本身更重要）

### 事故 1：测试假绿

**现象**：`test_parse_rejects_shell_injection` 在修复前显示 passed。

**真相**：
1. Windows 没有 `file` 命令，`shell=True` 执行失败
2. 输出是 GBK，`text=True` 按 UTF-8 解码抛异常
3. 捕获的 stdout 为空 → "注入标记不在输出里" 恰好成立

**教训**：**用"输出里没有某个字符串"判断注入是否被防住，会被编码和环境差异骗过。断言调用形态（`shell=False` + 参数列表）才可靠。**

### 事故 2：门禁假绿

**现象**：`sca-scan` 首次运行显示 success。

**真相**：日志里 `Number of language-specific files num=0` —— Trivy 一个依赖文件都没识别到，扫了个空。

两次原因：
1. `reports/` 目录不存在 → Trivy 写报告失败（是先红后才发现）
2. `requirements-lock.txt` 不被识别（Trivy 只认 `requirements*.txt` 这类命名）
3. 根本原因：`requirements.txt` 用 `>=`，**版本不确定的包会被 Trivy 直接跳过**

**处置**：`requirements.txt` 改为固定版本，日志确认 `num=1` 才算绿。

**教训**：**"绿"必须能被证据支撑。** 一个从不报错的扫描器，和一个没有扫描的扫描器，在 PR 页面上看起来完全一样。

## 四、一条经验

三个工具的门禁策略**必须不同**：

- Gitleaks：零容忍（密钥泄露没有"部分可接受"）
- Semgrep：按规则严重度（误报可通过调规则消化）
- Trivy：只阻断 HIGH/CRITICAL 且有修复方案的（否则会被"上游还没修"的 CVE 长期卡死）

如果用同一把尺子量三件事，门禁不是太松就是太紧，最后都会被绕过。
