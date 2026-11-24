"""评测集与快照的读取，以及评测集指纹计算。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def load_jsonl(path: str | Path) -> list[dict]:
    records: list[dict] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def load_evalset(path: str | Path) -> list[dict]:
    return load_jsonl(path)


def load_snapshot(path: str | Path) -> tuple[dict[str, dict], str]:
    """返回 (case_id -> 记录, 快照声明的模型名)。

    模型名用于在报告里标注数据来源：
    bootstrap 占位数据会带 model=bootstrap-simulated，报告需明确警告。
    """
    mapping: dict[str, dict] = {}
    model = "unknown"
    for rec in load_jsonl(path):
        mapping[rec["case_id"]] = rec
        model = rec.get("model", model)
    return mapping, model


def evalset_fingerprint(path: str | Path) -> str:
    """评测集指纹，写进报告供人工核对"这次算的是哪一版真值"。"""
    data = Path(path).read_bytes()
    return hashlib.sha256(data).hexdigest()[:16]
