#!/usr/bin/env bash
# 抽取准确率评测。固定回放快照，不联网、不需要 API key。
set -euo pipefail
mkdir -p reports
export EXTRACTOR_BACKEND=replay
python -m scripts.run_eval \
  --evalset evalsets/v1.jsonl \
  --prompt-version "${PROMPT_VERSION:-v1}" \
  --policy eval/policy.yaml \
  --report reports/eval-report.md
