#!/usr/bin/env bash
# E2E 冒烟。CI 环境设 CI=true，conftest 会用 Playwright 自带 Chromium 而非系统 Chrome。
set -euo pipefail
mkdir -p reports
python -m playwright install --with-deps chromium
python -m pytest tests/test_e2e.py -v --junitxml=reports/e2e-results.xml
