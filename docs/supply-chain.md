# 镜像供应链：构建 → 扫描 → 签名 → 准入

> 阶段四的目标不是"把镜像签个名"，而是**证明签名本身不构成任何控制**，
> 只有准入控制器在部署时校验，才真正阻止未签名镜像运行。

## 一、四层结构

| 层 | 做什么 | 在哪 | 失败会怎样 |
|---|---|---|---|
| **构建** | 多阶段构建，运行镜像非 root | `Dockerfile` | 镜像起不来 / 以 root 运行 |
| **扫描** | Trivy 扫镜像层（OS 包 + Python 包） | `image-pipeline` | 带 HIGH/CRITICAL 的镜像被拦 |
| **签名** | Cosign 按 digest 签名并推 GHCR | `image-pipeline` | 无签名镜像 |
| **准入** | Kyverno 在 Pod 创建时校验签名 | `admission-verify` | 未签名镜像被拒绝 |

七个门禁全部是 `dev` / `main` 的 required check。

## 二、红绿实验证据

### 红 A · 没有策略时，未签名镜像能跑

```
✅ 未启用策略时，未签名镜像成功运行 —— 证明签名本身不构成控制
pod/probe-unsigned condition met
```

**这一半常被跳过，但它才是关键**：如果只做红 B，你会以为"签了名就安全了"。
红 A 证明的是——**仓库里躺着签名，集群照样接受未签名镜像**。

### 红 B · 启用策略后，签名放行、未签名被拒

```
--- 已签名镜像应当被放行 ---
pod/probe-signed condition met
✅ 已签名镜像正常准入

--- 未签名镜像应当被拒绝 ---
Error from server: admission webhook "ivpol.validate.kyverno.svc-fail-finegrained-verify-image-signature"
  denied the request: 镜像未通过签名验证
  attestor "cosign": failed to verify cosign signatures: no signatures found
✅ 未签名镜像被准入控制器拒绝
```

**对照物怎么造**：用 `docker build --label` 构建同内容不同 digest 的镜像。
不能复用已签名镜像改 tag——签名绑定 digest，同一内容换 tag 签名依然有效。

## 三、八个坑（按踩到的顺序）

| # | 现象 | 根因 | 解法 |
|---|---|---|---|
| 1 | `/requirements-app.txt: not found` | `.dockerignore` 排除了 Dockerfile 要 COPY 的文件 | 从 ignore 列表移除 |
| 2 | 拉不到 frontend 镜像 | `# syntax=docker/dockerfile:1` 要访问 docker.io | 删掉该指令（未用新语法） |
| 3 | CRD 注解超 256KB | 客户端 apply 把整个 manifest 存进 `last-applied-configuration` | `kubectl apply --server-side=true` |
| 4 | Kyverno 拒收策略 | v1.20 废弃 legacy `kyverno.io/v1 ClusterPolicy` | 迁移到 `policies.kyverno.io/v1 ImageValidatingPolicy` |
| 5 | `unknown field insecureIgnoreTlog` | 该字段属于 keyless 模式，不在 key attestor 下 | 删除 |
| 6 | **已签名镜像也验签失败** | BuildKit 默认加 provenance，镜像变 manifest list，签名签的 digest 与验证解析的 digest 不同 | `docker build --provenance=false` |
| 7 | 准入说读不到签名 | 一度误判为"私有包"，实测匿名可拉（HTTP 200），**包是 public** | — |
| 8 | `offline verification failed` 持续出现 | 签名时用了 `--tlog-upload=false`，签名里没有透明日志条目 | 去掉该参数，正常上传 tlog |

### 第 8 个坑的教训

我一开始为了"减少对外部依赖"，主动关掉了 tlog 上传，还在注释里写"生产环境应当开启"。

结果就是准入验证失败。本地用 cosign 复现了这个错误：

```
Error: no matching signatures: signature not found in transparency log
```

**结论：透明日志不是可选的附加项，它是签名完整性的一部分。**
为了"省一个外部依赖"而关掉它，等于把签名降级成一个自说自话的标签。

### 第 7 个坑的教训

我根据 `offline verification failed` 判断"包是私有的"，让用户去改可见性。
实测匿名请求 manifest 返回 **HTTP 200**——包本来就是 public。

**教训：报错信息里的"offline"不等于"没权限"。**
`offline verification failed` 在 cosign 语境里指"签名无法被独立验证"，不是"连不上仓库"。
先做最小验证（匿名 curl），再下结论。

## 四、三个关键设计决定

### 1. 按 digest 签名，不按 tag

```bash
cosign sign --key ... ghcr.io/owner/repo@sha256:<digest>
```

tag 是可变的（谁都能 `docker push` 覆盖 `:latest`），digest 是内容寻址的。
签 tag 等于给一个"可能明天指向别的镜像"的指针签名。

### 2. 运行时依赖与测试依赖分文件

`requirements.txt` 含 pytest / playwright，`requirements-app.txt` 只含 3 个运行时包。
镜像里不带测试框架，体积更小、攻击面更小、Trivy 报的无关 CVE 更少。

### 3. 卸载 pip / setuptools / wheel

运行期不需要包管理器。卸掉之后：
- 攻击面减小（镜像里没有可以 `pip install` 的东西）
- pip 的 vendored 包（urllib3 等）随之消失，CVE 数量下降

初版镜像的 9 个 HIGH/CRITICAL **全部来自底座**（libzstd1 / setuptools / urllib3 / msgpack），
不是我们自己装的依赖——这正是"镜像扫描"与"依赖扫描"的区别。

## 五、这个方案的生产差距

| 项 | 本项目 | 生产做法 |
|---|---|---|
| 私钥管理 | GitHub Secrets 存加密私钥 | KMS / HSM / Vault，密钥不出硬件 |
| 签名身份 | 长期密钥对 | keyless + OIDC 短期证书（Sigstore Fulcio） |
| 准入旁路 | `validationActions: Deny` 写死 | `PolicyException` 带审批与到期时间 |
| 镜像仓库凭据 | 依赖包为 public | `imagePullSecrets` + 策略 `credentials` 块 |
| 基础镜像 CVE | `apt-get upgrade` 临时修补 | 定期重建 base image + 依赖机器人自动 PR |

这些差距不是"做得不够好"，而是**这个练习项目的边界**——把机制跑通、把坑踩明白，
比堆配置更接近真实的理解。
