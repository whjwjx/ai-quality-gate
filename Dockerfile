# syntax=docker/dockerfile:1
#
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

# 非 root 运行。固定 UID 便于在 K8s securityContext 里对齐 runAsUser。
RUN useradd --create-home --uid 10001 appuser

WORKDIR /app
# 只从 builder 拿装好的包，不复制 pip、wheel 等构建工具
COPY --from=builder /install /usr/local
COPY app/ ./app/

USER appuser
EXPOSE 8000

# slim 镜像没有 curl，用 python 自带 urllib 做健康检查
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2).status==200 else 1)"

# exec 形式（不用 shell），信号能直接传给 uvicorn 进程
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
