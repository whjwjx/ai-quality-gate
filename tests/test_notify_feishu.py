"""飞书通知的签名与 payload 测试。

签名算错的表现是"消息发不出去"，而且飞书返回的错误信息不明显，
所以在本地把这层锁死，比在 CI 里反复试便宜得多。
"""

from __future__ import annotations

from scripts.notify_feishu import build_payload, sign


def test_sign_is_deterministic():
    assert sign("my-secret", "1700000000") == sign("my-secret", "1700000000")


def test_sign_changes_with_timestamp():
    assert sign("s", "1700000000") != sign("s", "1700000001")


def test_sign_changes_with_secret():
    assert sign("a", "1700000000") != sign("b", "1700000000")


def test_payload_omits_signature_without_secret():
    p = build_payload("hello")
    assert p["msg_type"] == "text"
    assert p["content"]["text"] == "hello"
    assert "sign" not in p and "timestamp" not in p


def test_payload_includes_signature_with_secret():
    p = build_payload("hi", secret="abc", timestamp="1700000000")
    assert p["timestamp"] == "1700000000"
    assert p["sign"] == sign("abc", "1700000000")


def test_payload_content_is_plain_text():
    """多行中文不该被转义破坏 —— 这正是当初放弃 jq 拼 JSON 的原因。"""
    text = "🔴 dev 门禁失败\n失败项： sca-scan\n详情：https://x"
    p = build_payload(text)
    assert p["content"]["text"] == text
