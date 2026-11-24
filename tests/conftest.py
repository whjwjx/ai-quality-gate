"""pytest 全局 fixture：启动被测服务、管理数据清理、选择浏览器通道。"""

from __future__ import annotations

import os
import threading
import time

import pytest
import uvicorn

from app.main import _TENANT_DOCS, app


@pytest.fixture(scope="session")
def live_server():
    """在线程里启动 uvicorn，供 Playwright E2E 访问。"""
    config = uvicorn.Config(app, host="127.0.0.1", port=8123, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.1)
    yield "http://127.0.0.1:8123"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(autouse=True)
def clean_store():
    """每个用例前清空内存存储，保证用例独立可重复。"""
    _TENANT_DOCS.clear()
    yield
    _TENANT_DOCS.clear()


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    """本地用系统 Chrome（channel=chrome），CI 用 Playwright 自带的 Chromium。"""
    if not os.environ.get("CI"):
        return {**browser_type_launch_args, "channel": "chrome"}
    return browser_type_launch_args
