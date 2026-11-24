#!/usr/bin/env bash
# 安装依赖。CI 与本地共用，逻辑不写进 yaml。
set -euo pipefail
python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
