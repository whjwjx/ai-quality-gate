"""Trivy SARIF -> Issue 内容的转换测试。

这段逻辑决定「Issue 长什么样」，出错的表现是：标题看不懂、修复建议缺失、
标签分类错。这些都不会让 CI 变红，所以必须靠测试兜。
"""

from __future__ import annotations

import json

import pytest

from scripts.report_findings import parse_trivy_sarif

SAMPLE = {
    "runs": [
        {
            "results": [
                {
                    "ruleId": "CVE-2023-37920",
                    "message": {
                        "text": (
                            "Package: certifi\n"
                            "Installed Version: 2022.12.7\n"
                            "Vulnerability CVE-2023-37920\n"
                            "Severity: HIGH\n"
                            "Fixed Version: 2023.7.22\n"
                            "Link: https://avd.aquasec.com/xxx"
                        )
                    },
                    "locations": [
                        {"physicalLocation": {"artifactLocation": {"uri": "requirements.txt"}}}
                    ],
                },
                {
                    "ruleId": "CVE-2024-39689",
                    "message": {
                        "text": (
                            "Package: certifi\n"
                            "Installed Version: 2022.12.7\n"
                            "Severity: LOW\n"
                            "Fixed Version: 2024.7.4"
                        )
                    },
                    "locations": [
                        {"physicalLocation": {"artifactLocation": {"uri": "requirements.txt"}}}
                    ],
                },
            ]
        }
    ]
}


@pytest.fixture()
def findings(tmp_path):
    p = tmp_path / "trivy.sarif"
    p.write_text(json.dumps(SAMPLE, ensure_ascii=False), encoding="utf-8")
    return parse_trivy_sarif(p)


def test_parses_all_results(findings):
    assert len(findings) == 2
    assert findings[0].rule_id == "CVE-2023-37920"
    assert findings[1].rule_id == "CVE-2024-39689"


def test_extracts_package_and_versions(findings):
    f = findings[0]
    assert f.package == "certifi"
    assert f.installed == "2022.12.7"
    assert f.fixed == "2023.7.22"
    assert f.severity == "HIGH"


def test_title_is_readable(findings):
    title = findings[0].title
    assert "[HIGH]" in title
    assert "certifi" in title
    assert "CVE-2023-37920" in title


def test_labels_carry_severity(findings):
    labels = findings[0].labels
    assert "security" in labels
    assert "deps" in labels
    assert "severity:high" in labels


def test_body_contains_fix_hint(findings):
    body = findings[0].body
    assert "升级到 2023.7.22" in body
    assert "requirements.txt" in body


def test_body_handles_missing_fix():
    """没有修复版本时给出'评估影响'的指引，而不是空白。"""
    from scripts.report_findings import Finding

    f = Finding(
        rule_id="CVE-X", location="requirements.txt", package="foo",
        installed="1.0", fixed="", severity="MEDIUM", raw_message="m",
    )
    assert "暂无修复版本" in f.body
