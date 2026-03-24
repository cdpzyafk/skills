#!/bin/bash
# 使用 uv run 确保 playwright / requests / beautifulsoup4 可用
# 用法与 fetch_upcoming_changes.py 完全相同，参数直接透传
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if command -v uv &>/dev/null; then
    exec uv run \
        --with playwright \
        --with requests \
        --with beautifulsoup4 \
        python3 "$SCRIPT_DIR/fetch_upcoming_changes.py" "$@"
else
    # 回退：直接用 python3（需要手动安装依赖）
    exec python3 "$SCRIPT_DIR/fetch_upcoming_changes.py" "$@"
fi
