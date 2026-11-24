#!/usr/bin/env bash
# API 测试 + JUnit 报告，供 CI 归档。
set -euo pipefail
mkdir -p reports
python -m pytest tests/test_api.py -v --junitxml=reports/api-results.xml
