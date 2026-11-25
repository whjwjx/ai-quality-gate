# 多阶段构建：builder 只负责装依赖，运行镜像里不留 pip 缓存和编译产物。
# 这样做的收益：镜像更小、攻击面更小、Trivy 扫出来的无关 CVE 更少。

# ---------- 构建阶段 ----------
FROM python:3.13-slim AS builder

WORKDIR /build
# 先只拷依赖清单，让「依赖没变」时这一层能命中缓存
COPY requirements-app.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements-app.txt

# ---------- 运行阶段 ----------
FROM python:3.13-slim

# 底座自带的 OS 包会带 CVE（镜像扫描扫的就是这些，依赖扫描看不到）。
# 升级到当前安全版本；--no-install-recommends 避免顺手装进无关包。
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /install /usr/local

# 运行期用不到 pip / setuptools / wheel，直接卸掉：
#   1. 减少攻击面（镜像里不该有包管理器）
#   2. pip 自带的 vendored 包（urllib3 等）会随之一并消失，CVE 数量随之下降
RUN python -m pip uninstall -y pip setuptools wheel || true

# 非 root 运行。固定 UID 便于在 K8s securityContext 里对齐 runAsUser。
RUN useradd --create-home --uid 10001 appuser
COPY app/ ./app/

USER appuser
EXPOSE 8000

# slim 镜像没有 curl，用 python 自带 urllib 做健康检查
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2).status==200 else 1)"

# exec 形式（不用 shell），信号能直接传给 uvicorn 进程
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
