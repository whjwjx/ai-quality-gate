#!/usr/bin/env bash
# API 测试 + JUnit 报告，供 CI 归档。
set -euo pipefail
mkdir -p reports
# 跑全部单元测试（排除需要浏览器的 E2E，它由 test_e2e.sh 单独跑）
python -m pytest tests/ -v --junitxml=reports/api-results.xml --ignore=tests/test_e2e.py
