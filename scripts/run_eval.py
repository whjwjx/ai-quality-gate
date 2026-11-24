"""评测判定脚本：字段级准确率 / 文档级准确率 / P-R-F1 / 注入通过率。

设计要点：
- 只依赖 Extractor 接口，回放与真实调用共用同一套判定
- 报告包含评测集指纹与快照来源，便于人工核对"算的是哪一版"
- 任一指标低于 policy 阈值即返回非零退出码，直接中断 CI

用法：
    python -m scripts.run_eval --evalset evalsets/v1.jsonl --prompt-version v1
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from eval.extractor import make_extractor
from eval.loader import evalset_fingerprint, load_evalset
from eval.schema import expected_fields, normalize

_CODE_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


def parse_json_loose(raw: str) -> dict | None:
    """模型输出可能带 Markdown 代码块或前后缀，这里做容错解析。"""
    text = _CODE_FENCE.sub("", raw.strip())
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def load_policy(path: str | Path) -> dict[str, float]:
    policy: dict[str, float] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        policy[key.strip()] = float(value.strip())
    return policy


def run(evalset_path: str, prompt_version: str, policy_path: str, report_path: str,
        snapshot: str | None = None) -> int:
    cases = load_evalset(evalset_path)
    policy = load_policy(policy_path)
    extractor = make_extractor(prompt_version, snapshot)

    tp = fp = fn = 0
    field_total = 0
    field_correct = 0
    doc_correct = 0
    field_stat: dict[str, list[int]] = {}
    failures: list[str] = []
    injection_failures: list[str] = []
    injection_total = 0

    for case in cases:
        raw = extractor.extract(case)
        parsed = parse_json_loose(raw)
        gold = case.get("gold_fields", {})
        fields = expected_fields(case["doc_type"])
        case_all_correct = True

        for field in fields:
            field_total += 1
            stat = field_stat.setdefault(field, [0, 0])  # [correct, total]
            stat[1] += 1

            gold_val = normalize(field, gold.get(field))
            pred_val = normalize(field, (parsed or {}).get(field))

            if gold_val is not None and pred_val is not None and gold_val == pred_val:
                tp += 1
                field_correct += 1
                stat[0] += 1
            elif gold_val is not None and pred_val is not None:
                fp += 1
                fn += 1
                case_all_correct = False
                failures.append(
                    f"`{case['case_id']}` / `{field}`：期望 `{gold_val}`，实际 `{pred_val}`"
                )
            elif gold_val is not None:
                fn += 1
                case_all_correct = False
                failures.append(f"`{case['case_id']}` / `{field}`：漏抽（期望 `{gold_val}`）")
            elif pred_val is not None:
                fp += 1
                case_all_correct = False
                failures.append(f"`{case['case_id']}` / `{field}`：幻觉（不该有值，实际 `{pred_val}`）")

        if case_all_correct:
            doc_correct += 1

        # 注入断言：输出里不得出现指定字符串，且必须仍是合法 JSON
        injection = case.get("injection")
        if injection:
            injection_total += 1
            leaked = [s for s in injection.get("must_not_contain", []) if s in raw]
            if leaked or parsed is None:
                reason = f"泄露片段 {leaked}" if leaked else "输出不是合法 JSON"
                injection_failures.append(
                    f"`{case['case_id']}`（{injection.get('type')}）：{reason}"
                )

    field_acc = field_correct / field_total if field_total else 0.0
    doc_acc = doc_correct / len(cases) if cases else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    inj_rate = (injection_total - len(injection_failures)) / injection_total if injection_total else 1.0

    model_name = getattr(extractor, "model", "unknown")
    is_bootstrap = "bootstrap" in str(model_name).lower()
    fingerprint = evalset_fingerprint(evalset_path)

    checks = [
        ("字段级准确率", field_acc, policy.get("field_accuracy", 0.0)),
        ("文档级准确率", doc_acc, policy.get("doc_accuracy", 0.0)),
        ("注入通过率", inj_rate, policy.get("injection_pass_rate", 0.0)),
    ]
    failed = [(name, val, thr) for name, val, thr in checks if val < thr]
    passed = not failed

    lines: list[str] = []
    lines.append("# 抽取准确率评测报告")
    lines.append("")
    if is_bootstrap:
        lines.append("> ⚠️ **快照来源为 bootstrap 占位数据，非真实模型输出。** 该报告仅用于验证链路，不可作为发布依据。")
        lines.append("")
    lines.append(f"- 评测集：`{evalset_path}`")
    lines.append(f"- 评测集指纹：`{fingerprint}`")
    lines.append(f"- prompt 版本：`{prompt_version}`")
    lines.append(f"- 快照模型：`{model_name}`")
    lines.append(f"- 用例数：{len(cases)}")
    lines.append(f"- 生成时间：{datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    lines.append("")
    lines.append("## 指标")
    lines.append("")
    lines.append("| 指标 | 实际 | 阈值 | 结果 |")
    lines.append("|---|---|---|---|")
    for name, val, thr in checks:
        mark = "✅" if val >= thr else "❌"
        lines.append(f"| {name} | {val:.2%} | {thr:.2%} | {mark} |")
    lines.append("")
    lines.append("## 分类指标")
    lines.append("")
    lines.append(f"- 精确率 Precision：{precision:.2%}")
    lines.append(f"- 召回率 Recall：{recall:.2%}")
    lines.append(f"- F1：{f1:.2%}")
    lines.append(f"- TP={tp} FP={fp} FN={fn}")
    lines.append("")
    lines.append("## 各字段准确率")
    lines.append("")
    lines.append("| 字段 | 正确 / 总数 | 准确率 |")
    lines.append("|---|---|---|")
    for field, (ok, total) in sorted(field_stat.items()):
        lines.append(f"| `{field}` | {ok}/{total} | {(ok / total if total else 0):.0%} |")
    lines.append("")

    if injection_failures:
        lines.append("## 注入防御失败")
        lines.append("")
        for item in injection_failures:
            lines.append(f"- {item}")
        lines.append("")

    if failures:
        lines.append("## 失败样本")
        lines.append("")
        for item in failures:
            lines.append(f"- {item}")
        lines.append("")

    lines.append("## 结论")
    lines.append("")
    if passed:
        lines.append("✅ 全部指标达到阈值，允许发布。")
    else:
        lines.append("❌ 以下指标未达阈值，阻断发布：")
        for name, val, thr in failed:
            lines.append(f"- {name}：{val:.2%} < {thr:.2%}")
    report = "\n".join(lines) + "\n"

    report_file = Path(report_path)
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(report, encoding="utf-8")

    print(report)
    print(f"[eval] 报告已写入 {report_file}")
    return 0 if passed else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="文档抽取准确率评测")
    parser.add_argument("--evalset", default="evalsets/v1.jsonl")
    parser.add_argument("--prompt-version", default="v1")
    parser.add_argument("--policy", default="eval/policy.yaml")
    parser.add_argument("--report", default="reports/eval-report.md")
    parser.add_argument("--snapshot", default=None, help="快照子目录名，默认 deepseek")
    args = parser.parse_args(argv)
    return run(args.evalset, args.prompt_version, args.policy, args.report, args.snapshot)


if __name__ == "__main__":
    sys.exit(main())
