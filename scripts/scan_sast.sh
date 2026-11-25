#!/usr/bin/env bash
# 静态代码分析。规则在 security/semgrep-rules.yaml。
#
# --error：只要出现 ERROR 级别的发现就以非零退出码结束，直接中断 CI。
# --sarif：同时产出 SARIF，可被 GitHub Code Scanning 消费。
set -euo pipefail
mkdir -p reports

semgrep scan \
  --config security/semgrep-rules.yaml \
  --error \
  --sarif \
  --output reports/semgrep.sarif \
  --quiet
