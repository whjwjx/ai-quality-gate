"""本地用真实模型录制快照。CI 中绝不运行。

用法：
    # 确保已设 DEEPSEEK_API_KEY
    python -m scripts.record_snapshot --evalset evalsets/v1.jsonl --prompt-version v1

产物：snapshots/deepseek/prompt_v1.jsonl
换 prompt 版本或新增用例后必须重录，否则回放会因缺少 case 而报错。
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from eval.extractor import LLMExtractor, load_prompt
from eval.loader import load_evalset, load_snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="录制模型响应快照")
    parser.add_argument("--evalset", default="evalsets/v1.jsonl")
    parser.add_argument("--prompt-version", default="v1")
    parser.add_argument("--snapshot", default="deepseek", help="快照子目录名")
    parser.add_argument("--append", action="store_true", help="只补录快照里缺失的用例")
    args = parser.parse_args(argv)

    snapshot_dir = Path("snapshots") / args.snapshot
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    out_path = snapshot_dir / f"prompt_{args.prompt_version}.jsonl"

    load_prompt(args.prompt_version)  # 提前校验 prompt 文件存在
    cases = load_evalset(args.evalset)

    existing: dict[str, dict] = {}
    if args.append and out_path.exists():
        existing, _ = load_snapshot(out_path)

    extractor = LLMExtractor(args.prompt_version)
    records: dict[str, dict] = dict(existing)

    for case in cases:
        cid = case["case_id"]
        if cid in records:
            print(f"[skip] {cid} 已有快照")
            continue
        raw = extractor.extract(case)
        records[cid] = {
            "case_id": cid,
            "prompt_version": args.prompt_version,
            "model": extractor.model,
            "raw_response": raw,
            "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        print(f"[record] {cid}")

    with out_path.open("w", encoding="utf-8") as fh:
        for case in cases:  # 按评测集顺序写，便于 diff
            rec = records.get(case["case_id"])
            if rec:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"[done] {len(records)} 条 → {out_path}")
    print(f"[hint] prompt 版本 {args.prompt_version}，模型 {extractor.model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
