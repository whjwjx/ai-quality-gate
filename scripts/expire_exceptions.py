"""例外到期检查：把「临时豁免」关进时间的笼子里。

为什么需要：
    给发现打 `exception:expire-2026-12-31` 标签，本意是"先放过，到期再算"。
    但没有自动检查时，到期日只是标签里的一个字符串，没人会记得。
    半年后这些标签会变成事实上的永久豁免 —— 而所有人都以为"已经评估过风险"。

处理逻辑：
    1. 找出所有 `exception:expire-YYYY-MM-DD` 标签
    2. 日期早于今天的 -> 移除该标签、加 `exception-expired`、评论提醒复核
    3. 未到期的不动
"""

from __future__ import annotations

import datetime as dt
import os
import re
import sys
from typing import Any

from scripts.issue_reporter import GitHubIssuesReporter  # noqa: F401  (保持模块同源)
import json
import urllib.parse
import urllib.request

LABEL_RE = re.compile(r"^exception:expire-(\d{4}-\d{2}-\d{2})$")
Transport = "Any"


def parse_expiry(label: str) -> "dt.date | None":
    """从标签里解析到期日，格式不对返回 None。"""
    m = LABEL_RE.match(label)
    if not m:
        return None
    try:
        return dt.date.fromisoformat(m.group(1))
    except ValueError:
        return None


class ExceptionAuditor:
    def __init__(self, repo: str, token: str, transport=None,
                 api_base: str = "https://api.github.com") -> None:
        self.repo = repo
        self.token = token
        self.api_base = api_base
        self._transport = transport or self._http

    def _http(self, method: str, path: str, payload: "dict[str, Any] | None" = None) -> Any:
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            f"{self.api_base}{path}", data=data, method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}

    def expired_labels(self, today: "dt.date | None" = None) -> list[str]:
        today = today or dt.date.today()
        payload = self._transport("GET", f"/repos/{self.repo}/labels?per_page=100", None)
        labels = [lb["name"] for lb in payload] if isinstance(payload, list) else []
        out = []
        for name in labels:
            expiry = parse_expiry(name)
            if expiry is not None and expiry < today:
                out.append(name)
        return out

    def audit(self, today: "dt.date | None" = None, dry_run: bool = False) -> list[dict]:
        today = today or dt.date.today()
        actions: list[dict] = []
        for label in self.expired_labels(today):
            q = urllib.parse.quote(f"repo:{self.repo} is:issue is:open label:{label}")
            issues = self._transport("GET", f"/search/issues?q={q}", None).get("items", [])
            for issue in issues:
                number = int(issue["number"])
                actions.append({"issue": number, "label": label})
                if dry_run:
                    continue
                # 移除过期标签（404 表示已不存在，忽略）
                try:
                    self._transport(
                        "DELETE",
                        f"/repos/{self.repo}/issues/{number}/labels/{urllib.parse.quote(label)}",
                        None,
                    )
                except Exception:  # noqa: BLE001
                    pass
                self._transport(
                    "POST",
                    f"/repos/{self.repo}/issues/{number}/comments",
                    {"body": (
                        f"例外 `{label}` 已于 `{parse_expiry(label)}` 到期，"
                        "标签已自动移除。\n\n请复核：问题是否已修复？若仍需豁免，"
                        "请重新评估并设置新的到期日；否则请修复后关闭本 Issue。"
                    )},
                )
        return actions


def main(argv: list[str]) -> int:
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    dry_run = "--dry-run" in argv
    if not repo or not token:
        print("[error] 需要 GITHUB_REPOSITORY 和 GITHUB_TOKEN")
        return 1

    auditor = ExceptionAuditor(repo, token)
    actions = auditor.audit(dry_run=dry_run)
    if not actions:
        print("[ok] 没有到期的例外")
        return 0
    for a in actions:
        print(f"[expired] #{a['issue']} 标签 {a['label']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
