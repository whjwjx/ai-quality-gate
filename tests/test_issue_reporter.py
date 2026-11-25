"""IssueReporter 的单元测试（金字塔底层：不联网、不依赖 GitHub）。

重点验证幂等：同一个指纹上报两次，只能有一个 Issue。
这类逻辑用集成测试验证成本很高（要真建单），用单测几毫秒就能覆盖。
"""

from __future__ import annotations

import urllib.parse

import pytest

from scripts.issue_reporter import GitHubIssuesReporter, ReportResult, fingerprint


class FakeTransport:
    """内存版 GitHub Issues API，只实现用到的那三个端点。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict | None]] = []
        self.issues: dict[int, dict] = {}
        self._next = 1

    def __call__(self, method: str, path: str, payload: dict | None) -> dict:
        self.calls.append((method, path, payload))

        if path.startswith("/search/issues"):
            query = urllib.parse.unquote(path)
            # 从查询串里抠出指纹，若某条 issue 的 body 含该标记则命中
            if "finding-fingerprint:" in query:
                tail = query.split("finding-fingerprint:")[1]
                fp = tail.split()[0]  # 取到空白为止，避开后面的 " -->" 等字符
                for number, issue in self.issues.items():
                    if f"finding-fingerprint:{fp} -->" in issue["body"]:
                        return {"items": [{"number": number}]}
            return {"items": []}

        if path.endswith("/labels"):
            return {}

        if method == "POST" and path.endswith("/issues"):
            number = self._next
            self._next += 1
            self.issues[number] = {
                "title": payload["title"],
                "body": payload["body"],
            }
            return {"number": number, "html_url": f"https://example.test/{number}"}

        if method == "PATCH":
            number = int(path.rsplit("/", 1)[1])
            self.issues[number]["body"] = payload["body"]
            return {"number": number, "html_url": f"https://example.test/{number}"}

        raise AssertionError(f"未预期的请求: {method} {path}")


@pytest.fixture()
def reporter():
    transport = FakeTransport()
    return GitHubIssuesReporter("owner/repo", "fake-token", transport=transport), transport


def test_fingerprint_is_stable():
    a = fingerprint("CVE-2023-37920", "requirements.txt")
    b = fingerprint("CVE-2023-37920", "requirements.txt")
    assert a == b
    assert len(a) == 12


def test_fingerprint_differs_by_location():
    assert fingerprint("CVE-1", "a.txt") != fingerprint("CVE-1", "b.txt")


def test_first_report_creates_issue(reporter):
    r, transport = reporter
    result = r.report(
        fp="abc123def456",
        title="[HIGH] certifi 存在已知漏洞",
        body="发现细节...",
        labels=["security", "deps"],
    )
    assert isinstance(result, ReportResult)
    assert result.created is True
    assert result.number == 1
    assert any(m == "POST" and p.endswith("/issues") for m, p, _ in transport.calls)


def test_second_report_updates_instead_of_creating(reporter):
    """幂等的核心断言：同一指纹第二次上报只更新，不新建。"""
    r, transport = reporter
    first = r.report(fp="abc123def456", title="t", body="v1", labels=["security"])
    second = r.report(fp="abc123def456", title="t", body="v2", labels=["security"])

    assert first.created is True
    assert second.created is False
    assert second.number == first.number
    # 只应有一次创建
    posts = [c for c in transport.calls if c[0] == "POST" and c[1].endswith("/issues")]
    assert len(posts) == 1
    # body 被更新到 v2
    assert "v2" in transport.issues[first.number]["body"]


def test_different_fingerprint_creates_new_issue(reporter):
    r, transport = reporter
    a = r.report(fp="aaaaaaaaaaaa", title="问题 A", body="x", labels=["security"])
    b = r.report(fp="bbbbbbbbbbbb", title="问题 B", body="y", labels=["security"])
    assert a.number != b.number
    assert b.created is True


def test_body_contains_hidden_marker(reporter):
    """隐藏标记是去重的依据，必须真的写进 body。"""
    r, transport = reporter
    result = r.report(fp="abc123def456", title="t", body="detail", labels=[])
    assert "<!-- finding-fingerprint:abc123def456 -->" in transport.issues[result.number]["body"]


def test_label_failure_does_not_block_issue_creation():
    """建 label 失败（如已存在返回 422）不应影响建单。"""

    class LabelsFail(FakeTransport):
        def __call__(self, method, path, payload):
            if path.endswith("/labels"):
                raise RuntimeError("422 label already exists")
            return super().__call__(method, path, payload)

    transport = LabelsFail()
    r = GitHubIssuesReporter("owner/repo", "t", transport=transport)
    result = r.report(fp="abc123def456", title="t", body="b", labels=["security"])
    assert result.created is True
