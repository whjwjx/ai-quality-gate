"""把扫描结果转成 GitHub Issue（目前处理 Trivy 的 SARIF）。

设计取舍：
    - 只处理「扫描失败时」的发现，扫描通过不建单。
    - 不自动关闭 Issue：修复是否彻底要人判断，自动关会掩盖"假修复"。
      闭环靠 PR 里写 `Closes #N`，让关闭动作和代码变更绑定在一起。
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from scripts.issue_reporter import GitHubIssuesReporter, fingerprint

# Trivy 的 SARIF message 是多行文本，形如：
#   Package: certifi\nInstalled Version: 2022.12.7\nVulnerability ...\nSeverity: HIGH
_FIELD = re.compile(r"^\s*(Package|Installed Version|Fixed Version|Severity):\s*(.+)$", re.M)


@dataclass(frozen=True)
class Finding:
    rule_id: str      # CVE-xxx / GHSA-xxx
    location: str     # requirements.txt
    package: str
    installed: str
    fixed: str
    severity: str
    raw_message: str

    @property
    def title(self) -> str:
        sev = self.severity.upper() or "UNKNOWN"
        pkg = self.package or self.location
        return f"[{sev}] {pkg} 存在已知漏洞（{self.rule_id}）"

    @property
    def labels(self) -> list[str]:
        sev = self.severity.lower() or "unknown"
        return ["security", "deps", f"severity:{sev}"]

    @property
    def body(self) -> str:
        fix_hint = (
            f"升级到 {self.fixed}"
            if self.fixed and self.fixed != "-"
            else "上游暂无修复版本，评估影响后可加例外标签"
        )
        return "\n".join(
            [
                f"**漏洞**：`{self.rule_id}`",
                f"**位置**：`{self.location}`",
                f"**受影响包**：`{self.package or '未知'}`",
                f"**当前版本**：`{self.installed or '未知'}`",
                f"**严重度**：{self.severity or 'UNKNOWN'}",
                f"**修复建议**：{fix_hint}",
                "",
                "<details><summary>扫描器原始输出</summary>",
                "",
                "```",
                self.raw_message.strip(),
                "```",
                "",
                "</details>",
                "",
                "---",
                "_由 CI 的 sca-scan 自动创建/更新；同一问题不会重复建单。_",
            ]
        )


def parse_trivy_sarif(path: Path) -> list[Finding]:
    data = json.loads(path.read_text(encoding="utf-8"))
    findings: list[Finding] = []
    for run in data.get("runs", []):
        for result in run.get("results", []):
            rule_id = result.get("ruleId", "unknown")
            locations = result.get("locations") or [{}]
            uri = (locations[0].get("physicalLocation", {})
                   .get("artifactLocation", {}).get("uri", "unknown"))
            message = result.get("message", {}).get("text", "")
            fields = {k: v.strip() for k, v in _FIELD.findall(message)}
            findings.append(
                Finding(
                    rule_id=rule_id,
                    location=uri,
                    package=fields.get("Package", ""),
                    installed=fields.get("Installed Version", ""),
                    fixed=fields.get("Fixed Version", ""),
                    severity=fields.get("Severity", ""),
                    raw_message=message,
                )
            )
    return findings


def main(argv: list[str]) -> int:
    sarif_path = Path(argv[1] if len(argv) > 1 else "reports/trivy.sarif")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GITHUB_TOKEN", "")

    if not sarif_path.exists():
        print(f"[skip] 没有找到扫描报告：{sarif_path}")
        return 0
    if not repo or not token:
        print("[error] 需要 GITHUB_REPOSITORY 和 GITHUB_TOKEN")
        return 1

    findings = parse_trivy_sarif(sarif_path)
    print(f"[info] 解析到 {len(findings)} 条发现")
    if not findings:
        return 0

    reporter = GitHubIssuesReporter(repo=repo, token=token)
    created = updated = 0
    for f in findings:
        fp = fingerprint(f.rule_id, f.location)
        result = reporter.report(fp=fp, title=f.title, body=f.body, labels=f.labels)
        if result.created:
            created += 1
            print(f"[new] #{result.number} {f.title}")
        else:
            updated += 1
            print(f"[update] #{result.number} {f.title}")

    print(f"[done] 新建 {created} 条，更新 {updated} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
