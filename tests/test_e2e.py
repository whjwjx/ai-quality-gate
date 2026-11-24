"""最小 E2E 冒烟：1 条 happy path + 1 条回归路径，不堆 UI 用例。"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Page, expect

SAMPLE_PDF = Path(__file__).resolve().parent / "fixtures" / "sample.pdf"


def test_upload_happy_path(page: Page, live_server: str):
    """上传 PDF 后页面显示 doc_id。"""
    page.goto(live_server)
    expect(page.locator("h1")).to_contain_text("DocExtract")

    SAMPLE_PDF.parent.mkdir(parents=True, exist_ok=True)
    SAMPLE_PDF.write_bytes(b"%PDF-1.4\n% smoke test fixture\n")

    page.set_input_files("#file", str(SAMPLE_PDF))
    page.click("#upload")
    expect(page.locator("#result")).to_contain_text("doc_id", timeout=5000)


def test_upload_rejects_bad_file(page: Page, live_server: str):
    """回归路径：上传非 PDF 时页面展示错误，不崩溃。"""
    page.goto(live_server)
    bad = SAMPLE_PDF.parent / "bad.txt"
    bad.write_bytes(b"not a pdf")
    page.set_input_files("#file", str(bad))
    page.click("#upload")
    expect(page.locator("#result")).to_contain_text("unsupported", timeout=5000)
