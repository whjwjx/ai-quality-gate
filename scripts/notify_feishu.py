"""向飞书群机器人推送消息，可选签名校验。

飞书自定义机器人如果开了「签名校验」，必须在请求体里带 timestamp 和 sign，
否则会被拒绝。签名算法是 HmacSHA256，key 是 secret，data 是
`timestamp + "\\n" + secret`，最后 base64。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.request


def sign(secret: str, timestamp: str) -> str:
    """按飞书规则算签名。"""
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(
        secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def build_payload(text: str, secret: str = "", timestamp: str = "") -> dict:
    """构造请求体。没有 secret 时不加签名字段（兼容未开启校验的机器人）。"""
    payload: dict = {"msg_type": "text", "content": {"text": text}}
    if secret:
        ts = timestamp or str(int(time.time()))
        payload["timestamp"] = ts
        payload["sign"] = sign(secret, ts)
    return payload


def send(webhook: str, text: str, secret: str = "") -> dict:
    payload = build_payload(text, secret)
    req = urllib.request.Request(
        webhook,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def main(argv: list[str]) -> int:
    webhook = os.environ.get("FEISHU_WEBHOOK", "")
    secret = os.environ.get("FEISHU_SECRET", "")
    text = argv[1] if len(argv) > 1 else "（空消息）"

    if not webhook:
        print("[error] 缺少 FEISHU_WEBHOOK")
        return 1

    try:
        result = send(webhook, text, secret)
    except Exception as exc:  # noqa: BLE001
        print(f"[error] 发送失败：{exc}")
        return 1

    # 飞书的成功标志是 code == 0
    if result.get("code") not in (0, None):
        print(f"[error] 飞书返回错误：{result}")
        return 1
    print(f"[ok] 已发送，响应：{result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
