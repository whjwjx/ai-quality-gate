"""靶子应用：最小文档抽取服务。

设计目的：为质量门禁、AI 评测、DevSecOps 三条实践线提供一个可控的被测系统。
故意埋了两颗种子缺陷，详见 SEEDED_ISSUES.md。不要用于生产。
"""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI(title="DocExtract - Quality Gate Demo", version="0.1.0")

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5MB
ALLOWED_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg"}
_TENANT_DOCS: dict[str, dict[str, object]] = {}

STATIC_DIR = Path(__file__).resolve().parent / "static"


class ExtractResponse(BaseModel):
    doc_id: str
    fields: dict[str, str]
    backend: str


def _get_owned_document(doc_id: str, tenant_id: str) -> dict[str, object]:
    """按 ID 取文档并校验租户归属。

    所有按 doc_id 访问资源的接口都必须走这里，避免再次出现 SEED-001 类型的越权。
    - 文档不存在 → 404
    - 文档属于其他租户 → 403（比 404 更明确，便于审计与排查）
    """
    doc = _TENANT_DOCS.get(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    if doc["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="forbidden: resource belongs to another tenant")
    return doc


class UploadResponse(BaseModel):
    doc_id: str
    tenant_id: str
    filename: str
    size: int


class DocumentResponse(BaseModel):
    doc_id: str
    tenant_id: str
    filename: str
    size: int


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    page = STATIC_DIR / "index.html"
    return HTMLResponse(content=page.read_text(encoding="utf-8"))


@app.post("/api/v1/documents/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    x_tenant_id: str = Header(..., min_length=1),
) -> UploadResponse:
    """上传文档：校验大小、后缀、MIME，按租户隔离存储。"""
    content = await file.read()

    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file too large")
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="empty file")

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=415, detail="unsupported file type")
    if file.content_type and not file.content_type.startswith(("application/pdf", "image/")):
        raise HTTPException(status_code=415, detail="unsupported media type")

    # 简单魔数校验：PDF 必须以 %PDF 开头
    if suffix == ".pdf" and not content.startswith(b"%PDF"):
        raise HTTPException(status_code=415, detail="PDF magic number mismatch")

    doc_id = str(uuid.uuid4())
    _TENANT_DOCS[doc_id] = {
        "tenant_id": x_tenant_id,
        "filename": file.filename,
        "size": len(content),
        "content": content,
    }
    return UploadResponse(
        doc_id=doc_id,
        tenant_id=x_tenant_id,
        filename=file.filename or "unnamed",
        size=len(content),
    )


@app.get("/api/v1/documents/{doc_id}", response_model=DocumentResponse)
def get_document(doc_id: str, x_tenant_id: str = Header(..., min_length=1)) -> DocumentResponse:
    """按 ID 读取文档元数据（已修复 SEED-001：校验租户归属）。"""
    doc = _get_owned_document(doc_id, x_tenant_id)
    return DocumentResponse(
        doc_id=doc_id,
        tenant_id=str(doc["tenant_id"]),
        filename=str(doc["filename"]),
        size=int(doc["size"]),
    )


@app.post("/api/v1/extract", response_model=ExtractResponse)
def extract_fields(doc_id: str, x_tenant_id: str = Header(..., min_length=1)) -> ExtractResponse:
    """字段抽取（回放占位版）。阶段 2 会接入可替换的 Extractor。"""
    _get_owned_document(doc_id, x_tenant_id)
    return ExtractResponse(
        doc_id=doc_id,
        fields={"doc_type": "unknown", "backend": "replay-stub"},
        backend="replay-stub",
    )


@app.post("/api/v1/documents/{doc_id}/parse")
def parse_document(doc_id: str, x_tenant_id: str = Header(..., min_length=1)) -> dict[str, str]:
    """调用系统工具解析文档（SEED-002 命令注入仍待修复）。"""
    doc = _get_owned_document(doc_id, x_tenant_id)
    filename = str(doc["filename"])
    result = subprocess.run(
        f"file {filename}",
        shell=True,
        capture_output=True,
        text=True,
    )
    return {"output": result.stdout, "returncode": str(result.returncode)}
