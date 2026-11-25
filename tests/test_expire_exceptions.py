"""例外到期逻辑测试。

这里最值得测的不是 HTTP 调用，而是日期判定：晚一天/早一天都意味着
"该豁免的没豁免"或"该收回的没收回"，两种都有人受害。
"""

from __future__ import annotations

import datetime as dt
import urllib.parse

import pytest

from scripts.expire_exceptions import ExceptionAuditor, parse_expiry


@pytest.mark.parametrize(
    "label,expected",
    [
        ("exception:expire-2026-12-31", dt.date(2026, 12, 31)),
        ("exception:expire-2020-01-01", dt.date(2020, 1, 1)),
        ("security", None),
        ("exception:expire-2026-13-01", None),   # 非法月份
        ("exception:expire-later", None),         # 非法格式
    ],
)
def test_parse_expiry(label, expected):
    assert parse_expiry(label) == expected


class FakeTransport:
    def __init__(self, labels, issues_by_label=None):
        self.labels = [{"name": n} for n in labels]
        self.issues_by_label = issues_by_label or {}
        self.calls = []

    def __call__(self, method, path, payload):
        self.calls.append((method, path))
        if path.startswith("/repos/") and "/labels?" in path:
            return self.labels
        if path.startswith("/search/issues"):
            decoded = urllib.parse.unquote(path)
            for label, items in self.issues_by_label.items():
                if label in decoded:
                    return {"items": items}
            return {"items": []}
        return {}


def test_expired_label_detected_only_after_due_date():
    labels = ["exception:expire-2026-01-10", "exception:expire-2027-01-01", "security"]
    auditor = ExceptionAuditor("o/r", "t", transport=FakeTransport(labels))

    assert auditor.expired_labels(dt.date(2026, 1, 9)) == []
    assert auditor.expired_labels(dt.date(2026, 1, 10)) == []      # 当天不算过期
    assert auditor.expired_labels(dt.date(2026, 1, 11)) == ["exception:expire-2026-01-10"]


def test_audit_removes_label_and_comments():
    labels = ["exception:expire-2026-01-10"]
    transport = FakeTransport(labels, {"exception:expire-2026-01-10": [{"number": 7}]})
    auditor = ExceptionAuditor("o/r", "t", transport=transport)

    actions = auditor.audit(today=dt.date(2026, 2, 1))

    assert actions == [{"issue": 7, "label": "exception:expire-2026-01-10"}]
    methods = [m for m, _ in transport.calls]
    assert "DELETE" in methods
    assert "POST" in methods


def test_dry_run_performs_no_writes():
    labels = ["exception:expire-2026-01-10"]
    transport = FakeTransport(labels, {"exception:expire-2026-01-10": [{"number": 7}]})
    auditor = ExceptionAuditor("o/r", "t", transport=transport)

    auditor.audit(today=dt.date(2026, 2, 1), dry_run=True)

    assert all(m == "GET" for m, _ in transport.calls), "试运行不应产生写操作"
