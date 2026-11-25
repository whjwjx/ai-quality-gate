"""把扫描发现上报为 GitHub Issue，并保证幂等。

为什么幂等是必需的：
    如果每次 CI 失败都建一个新 Issue，一天就能刷出几十条重复单，
    然后没人看了 —— 这比不建单更糟。Issue 的价值在于"可追踪"，
    而不是"有记录"。

指纹设计的关键决定：
    指纹里**不放行号**。含行号的话，代码上移一行、加个注释，同一个问题
    就会变成一条新 Issue，去重直接失效。所以指纹只由「规则 + 位置（文件）」
    决定，反映"同一个地方的同一种问题"。
"""

from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Protocol

MARKER = "<!-- finding-fingerprint:{fp} -->"

# transport(method, path, payload) -> 解析后的 JSON
Transport = Callable[[str, str, "dict[str, Any] | None"], dict[str, Any]]


def fingerprint(*parts: str) -> str:
    """由问题身份算出稳定短指纹。

    调用方传入的应该是「规则 ID + 文件路径 + 类别」这类稳定要素，
    不要传行号或时间戳。
    """
    raw = "|".join(p.strip() for p in parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:12]


@dataclass(frozen=True)
class ReportResult:
    number: int
    created: bool
    url: str


class IssueReporter(Protocol):
    """扫描结果 -> Issue 的上报接口。换实现（Jira / 飞书）时只改这一层。"""

    def report(
        self, *, fp: str, title: str, body: str, labels: list[str]
    ) -> ReportResult: ...


class GitHubIssuesReporter:
    """用 GITHUB_TOKEN 调 Issues API，不需要额外 PAT。"""

    def __init__(
        self,
        repo: str,
        token: str,
        transport: Transport | None = None,
        api_base: str = "https://api.github.com",
    ) -> None:
        self.repo = repo
        self.token = token
        self.api_base = api_base
        self._transport: Transport = transport or self._http

    def _http(
        self, method: str, path: str, payload: "dict[str, Any] | None" = None
    ) -> dict[str, Any]:
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            f"{self.api_base}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}

    def _find_open(self, fp: str) -> "int | None":
        """查是否已有同指纹的开放 Issue。用 body 里的隐藏标记搜索。"""
        marker = MARKER.format(fp=fp)
        query = f'repo:{self.repo} is:issue is:open in:body "{marker}"'
        result = self._transport(
            "GET", f"/search/issues?q={urllib.parse.quote(query)}", None
        )
        items = result.get("items") or []
        return int(items[0]["number"]) if items else None

    def _ensure_labels(self, labels: "list[str]") -> None:
        """确保 label 存在。已存在时 API 返回 422，忽略即可。

        建 label 失败不应阻断建单 —— 少个标签比丢条记录好。
        """
        for name in labels:
            try:
                self._transport(
                    "POST",
                    f"/repos/{self.repo}/labels",
                    {"name": name, "color": "ededed"},
                )
            except Exception:  # noqa: BLE001 - 标签是装饰，失败不影响主流程
                continue

    def report(
        self, *, fp: str, title: str, body: str, labels: list[str]
    ) -> ReportResult:
        body_with_marker = f"{body.rstrip()}\n\n{MARKER.format(fp=fp)}"
        existing = self._find_open(fp)

        if existing is not None:
            data = self._transport(
                "PATCH",
                f"/repos/{self.repo}/issues/{existing}",
                {"body": body_with_marker, "labels": labels},
            )
            return ReportResult(existing, created=False, url=data.get("html_url", ""))

        self._ensure_labels(labels)
        data = self._transport(
            "POST",
            f"/repos/{self.repo}/issues",
            {"title": title, "body": body_with_marker, "labels": labels},
        )
        return ReportResult(
            number=int(data["number"]),
            created=True,
            url=data.get("html_url", ""),
        )
