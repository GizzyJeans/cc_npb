#!/usr/bin/env bash
# 跑測試，並且在失敗時 **真的** 以非零狀態結束。
#
# 為什麼需要這支腳本
# ------------------
# 2026-09-13 的自動結算在一個全新容器裡執行，容器沒有裝 pytest。
# 當時用的指令是:
#
#     python3 -m pytest -q 2>&1 | tail -2 && git add -A && git commit ...
#
# 管線的結束狀態取自 **最後一個** 指令 (tail)，永遠是 0，所以 pytest
# 根本沒跑成功也一路 commit、push 下去了。輸出裡寫著
# "No module named pytest"，但 && 鏈條完全沒被擋住。
#
# 教訓有兩層:
#   1. 缺少工具要讓它 **失敗**，不能靜靜跳過 —— 跳過的測試比紅燈危險。
#   2. `cmd | tail && next` 這個寫法會吞掉 cmd 的結束狀態。要嘛
#      `set -o pipefail`，要嘛不要把要檢查的指令放進管線。
set -euo pipefail

cd "$(dirname "$0")/.."

if ! python3 -c 'import pytest' 2>/dev/null; then
    echo "pytest 未安裝 —— 自動安裝中（全新容器常見）"
    pip install --quiet pytest
fi

python3 -m pytest -q
