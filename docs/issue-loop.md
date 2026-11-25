# 发现闭环：从「红了一下」到「有人负责到底」

> 门禁只解决"不该进的进来了"。它不解决另外两个问题：
> **该知道的没人知道**（Pager 缺失），**知道了但没追踪没复盘**（Memory 缺失）。
> 阶段五补的是后者。

## 一、Gate / Pager / Memory 的分工

| 角色 | 回答什么问题 | 失效时的表现 | 本项目 |
|---|---|---|---|
| **Gate** | 不该进的进来了吗？ | 坏东西进主干 | ✅ 7 个门禁 |
| **Pager** | 该知道的知道了吗？ | 红了三天没人管 | ⬜ 未做 |
| **Memory** | 处理完了吗？能复盘吗？ | 同一个问题反复出现 | ✅ 本阶段 |

三者缺一个，质量体系就是断的：

- 只有 Gate：红了没人修，门禁变成"每天点 bypass"的仪式
- 只有 Pager：天天被叫醒，但不知道修了什么、还剩什么
- 只有 Memory：记录很漂亮，但坏东西照样进主干

## 二、幂等：这一阶段最容易做错的地方

**问题**：每次 CI 失败都建单，一天能刷出几十条重复 Issue，然后没人看。

**这比不建单更糟**——它会训练团队忽略 Issue 通知。

### 实现

```python
# 指纹只由「规则 + 文件」决定
def fingerprint(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:12]
```

**关键决定：指纹里不含行号。**

含行号的话，代码上移一行、加一行注释，同一个问题就变成"新问题"，去重直接失效。
指纹要表达的是"**同一个地方的同一种问题**"，不是"同一行代码"。

### 去重流程

```
指纹 = hash(规则ID + 文件路径)
   ↓
搜索已存在的开放 Issue 里是否含 <!-- finding-fingerprint:xxx -->
   ├─ 有 → PATCH 更新 body（刷新版本号和次数）
   └─ 无 → POST 新建
```

隐藏标记写在 Issue body 末尾，用 `in:body "标记"` 精确搜索。不污染标题，也不用给每个指纹建 label。

### 实测证据

第一次运行（引入 `certifi==2022.12.7`）：

```
#7  [CRITICAL] certifi 存在已知漏洞（GHSA-6q48-6c7w-9gw2）
#8  [HIGH] certifi 存在已知漏洞（CVE-2023-37920）
#9  [LOW] certifi 存在已知漏洞（CVE-2024-39689）
labels: security, deps, severity:critical/high/low
```

第二次运行（同样的代码，空提交触发）：

```
security 类 Issue 数量: 3     ← 没有变成 6
```

**3 条发现 = 3 个 Issue，重跑不新增。** 这才叫可用的闭环。

## 三、例外也要有到期日

给发现打 `exception:expire-2026-12-31`，本来是"先放过，到期再算"。

但没有自动检查时，到期日只是标签里的一个字符串——**半年后它会变成事实上的永久豁免，而所有人都以为"已经评估过风险"**。

`scripts/expire_exceptions.py` 的逻辑：

1. 找出所有 `exception:expire-YYYY-MM-DD` 标签
2. 日期 **早于** 今天的 → 移除标签 + 评论提醒复核
3. 未到期的不动

有个边界容易写错：**到期当天不算过**。`expiry < today` 而不是 `<=`，否则"12月31日到期"在 31 号一早就会被收走。

## 四、不自动关闭 Issue

扫描通过后，之前的 Issue 要不要自动关？

**不自动关。** 理由：

- 修复是否彻底要人判断，自动关会掩盖"假修复"（改了版本号但漏洞仍在）
- 关闭动作应该和代码变更绑定 —— 在 PR 里写 `Closes #7`，让"修好"和"关单"是同一个动作

自动关闭看起来很智能，实际会把"验证"这一步悄悄去掉。

## 五、标签体系

| 标签 | 用途 |
|---|---|
| `security` | 所有安全类发现 |
| `deps` / `sast` / `secrets` | 来源分类 |
| `severity:critical` / `high` / `low` | 严重度，用于排序和统计 |
| `exception:expire-YYYY-MM-DD` | 临时豁免，带到期日 |

**为什么用标签而不是 Issue 里的文字**：标签可搜索、可统计、可做趋势图。写在正文里的"高危"只能靠人读。

## 六、Pager：让"红了"变成"有人知道"

Memory 解决"有记录"，但不解决"有感知"。Issue 建了，如果你一整天不打开 GitHub，
等于没建。

### 实现

`notify-on-failure` job：门禁失败时推飞书群消息。

```yaml
if: always() && failure() && (github.ref == 'refs/heads/dev' || github.ref == 'refs/heads/main')
```

**这个条件里最重要的部分不是 `failure()`，是分支限制。**

如果 PR 失败也发消息，一天几十条，一周后所有人静音群 —— **那比不接告警更糟**。
告警的价值不在"发得多"，在"发的每条都值得看"。

### 飞书签名：一个反直觉的坑

飞书自定义机器人开启「签名校验」后，必须带 `timestamp` 和 `sign`。
算法看起来是标准 HMAC，但**参数位置和标准用法相反**：

```python
string_to_sign = f"{timestamp}\n{secret}"
# 飞书要求：stringToSign 当 key，消息体留空
digest = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
```

写成常见的 `hmac.new(key=secret, msg=stringToSign)` 会一直报：

```
{"code": 19021, "msg": "sign match fail or timestamp is not within one hour"}
```

这个错误信息同时提到"时间戳超时"，很容易误判成时钟问题。**实际是签名算法错了。**

### 告警内容

```
🔴 门禁失败
失败项： quality-gate sca-scan
提交：f59be24
作者：whjwjx
详情：https://github.com/.../actions/runs/...
```

`失败项` 是通过 `needs.<job>.result` 逐个判断拼出来的——只说"失败了"没有意义，
要说清**哪个门禁挂了**。

## 七、仍然缺的（度量层）

| 缺的 | 影响 |
|---|---|
| 高危 Issue 数量趋势 | 不知道质量在变好还是变坏 |
| MTTR（平均修复时长） | 无法回答"我们处理得多快" |
| on-call 轮值与升级 | 告警发了，但没规定谁必须响应 |

前两项是**度量**，第三项是**流程**。技术能保证"消息发出去"，保证不了"有人必须处理"。

**先把闭环做对，再谈度量**——没有可靠的 Issue 数据，趋势图只是噪音。

