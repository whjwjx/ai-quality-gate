"""API 自动化测试：fixture + 参数化覆盖正常 / 异常 / 边界 / 并发 / 越权。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

HEADERS_A = {"X-Tenant-ID": "tenant-a"}
HEADERS_B = {"X-Tenant-ID": "tenant-b"}


def pdf_bytes(size: int = 1024) -> bytes:
    return b"%PDF-1.4\n" + b"x" * size


@pytest.fixture
def uploaded_doc():
    """上传一个租户 A 的文档，返回 doc_id 供读取类用例复用。"""
    resp = client.post(
        "/api/v1/documents/upload",
        headers=HEADERS_A,
        files={"file": ("invoice.pdf", pdf_bytes(), "application/pdf")},
    )
    assert resp.status_code == 200
    return resp.json()["doc_id"]


# ---------- 正常路径 ----------

def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_upload_success():
    resp = client.post(
        "/api/v1/documents/upload",
        headers=HEADERS_A,
        files={"file": ("invoice.pdf", pdf_bytes(), "application/pdf")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tenant_id"] == "tenant-a"
    assert body["size"] > 0


def test_extract_fields(uploaded_doc):
    resp = client.post("/api/v1/extract", headers=HEADERS_A, params={"doc_id": uploaded_doc})
    assert resp.status_code == 200
    assert resp.json()["backend"] == "replay-stub"


# ---------- 异常 / 边界（参数化） ----------

@pytest.mark.parametrize(
    "filename,content,content_type,expected",
    [
        ("empty.pdf", b"", "application/pdf", 400),                       # 空文件
        ("huge.pdf", pdf_bytes(6 * 1024 * 1024), "application/pdf", 413),  # 大文件 >5MB
        ("fake.pdf", b"not a real pdf", "application/pdf", 415),           # 恶意文件：魔数不符
        ("evil.exe", b"MZ\x90", "application/octet-stream", 415),          # 异常格式
        ("script.PDF", b"%PDF-1.4", "text/html", 415),                     # MIME  spoof
    ],
)
def test_upload_rejects_bad_input(filename, content, content_type, expected):
    resp = client.post(
        "/api/v1/documents/upload",
        headers=HEADERS_A,
        files={"file": (filename, content, content_type)},
    )
    assert resp.status_code == expected, resp.text


def test_upload_requires_tenant_header():
    resp = client.post(
        "/api/v1/documents/upload",
        files={"file": ("invoice.pdf", pdf_bytes(), "application/pdf")},
    )
    assert resp.status_code == 422  # FastAPI 对缺失 header 返回 422


def test_get_nonexistent_document():
    resp = client.get("/api/v1/documents/does-not-exist", headers=HEADERS_A)
    assert resp.status_code == 404


# ---------- 并发上传 ----------

def test_concurrent_uploads():
    def upload(i):
        return client.post(
            "/api/v1/documents/upload",
            headers={"X-Tenant-ID": f"tenant-{i % 3}"},
            files={"file": (f"doc-{i}.pdf", pdf_bytes(64), "application/pdf")},
        ).status_code

    with ThreadPoolExecutor(max_workers=10) as pool:
        statuses = list(pool.map(upload, range(20)))
    assert all(code == 200 for code in statuses)


# ---------- 多租户越权（SEED-001 缺陷闭环） ----------

@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("GET", "/api/v1/documents/{doc_id}", None),
        ("POST", "/api/v1/extract?doc_id={doc_id}", None),
        ("POST", "/api/v1/documents/{doc_id}/parse", None),
    ],
)
def test_tenant_isolation_idor(uploaded_doc, method, path, payload):
    """租户 B 不应能通过任何接口读取/操作租户 A 的文档，统一期望 403。

    覆盖全部按 doc_id 访问资源的入口，防的是「新增接口忘记校验归属」这类复发问题。
    """
    url = path.format(doc_id=uploaded_doc)
    resp = client.request(method, url, headers=HEADERS_B, json=payload)
    assert resp.status_code == 403, f"{method} {url} 泄漏了跨租户资源：{resp.status_code}"


def test_owner_can_still_access(uploaded_doc):
    """回归保护：修复越权不能误伤正常访问——租户 A 仍能读自己的文档。"""
    resp = client.get(f"/api/v1/documents/{uploaded_doc}", headers=HEADERS_A)
    assert resp.status_code == 200
