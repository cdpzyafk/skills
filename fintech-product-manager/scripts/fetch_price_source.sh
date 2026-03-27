#!/usr/bin/env bash
# fetch_price_source.sh
# 价格源数据获取脚本：curl 优先，自动降级至 Playwright 截图
# 用法: ./fetch_price_source.sh <url> [--json-path <jq_filter>] [--screenshot-out <path>]
#
# 返回码:
#   0 = 成功（curl 或 Playwright）
#   1 = 两种方式都失败
#   2 = curl 失败，Playwright 截图已保存（需人工分析图片）

set -euo pipefail

URL="${1:-}"
JSON_PATH="${3:-}"         # jq filter，如 '.price' 或 '.data[0].markPx'
SCREENSHOT_OUT="${5:-/tmp/price_source_screenshot.png}"
TIMEOUT=15                 # curl 超时秒数

if [[ -z "$URL" ]]; then
  echo "Usage: $0 <url> [--json-path <jq_filter>] [--screenshot-out <path>]" >&2
  exit 1
fi

# ─── 参数解析 ───────────────────────────────────────────────────────────────
while [[ $# -gt 1 ]]; do
  case "$2" in
    --json-path)   JSON_PATH="$3";       shift 2 ;;
    --screenshot-out) SCREENSHOT_OUT="$3"; shift 2 ;;
    *) shift ;;
  esac
done

# ─── Step 1: curl 尝试 ───────────────────────────────────────────────────────
echo "▶ [curl] GET $URL"

HTTP_RESPONSE=$(curl -s -w "\n__STATUS__%{http_code}" \
  --max-time "$TIMEOUT" \
  -H "Accept: application/json, text/html, */*" \
  -H "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36" \
  "$URL" 2>/dev/null) || CURL_EXIT=$?

HTTP_BODY=$(echo "$HTTP_RESPONSE" | sed '$d')
HTTP_STATUS=$(echo "$HTTP_RESPONSE" | tail -n1 | sed 's/__STATUS__//')

CURL_FAILED=false

# 判断 curl 是否失败：超时/网络错误/403/429/空响应
if [[ ${CURL_EXIT:-0} -ne 0 ]]; then
  echo "  ✗ curl 网络错误 (exit=${CURL_EXIT:-0})" >&2
  CURL_FAILED=true
elif [[ "$HTTP_STATUS" =~ ^(403|404|429|5[0-9][0-9])$ ]]; then
  echo "  ✗ HTTP $HTTP_STATUS — 可能需要认证或被 WAF 拦截" >&2
  CURL_FAILED=true
elif [[ -z "$HTTP_BODY" ]]; then
  echo "  ✗ 响应体为空" >&2
  CURL_FAILED=true
fi

# 检测是否为 Next.js/React 动态页面（内容为 JS bundle，无真实数据）
if [[ "$CURL_FAILED" == "false" ]]; then
  JS_RENDER_SIGNALS=$(echo "$HTTP_BODY" | grep -c '_next/static\|__NEXT_DATA__\|ReactDOM\|<div id="root">' 2>/dev/null || true)
  if [[ "$JS_RENDER_SIGNALS" -gt 0 ]] && [[ -z "$JSON_PATH" ]]; then
    echo "  ⚠ 检测到 Next.js/React 动态渲染，纯文本内容不完整" >&2
    CURL_FAILED=true
  fi
fi

# curl 成功且指定了 JSON 路径 → 提取字段
if [[ "$CURL_FAILED" == "false" ]]; then
  if [[ -n "$JSON_PATH" ]] && command -v jq &>/dev/null; then
    RESULT=$(echo "$HTTP_BODY" | jq -r "$JSON_PATH" 2>/dev/null) || {
      echo "  ⚠ jq 解析失败，返回原始响应" >&2
      echo "$HTTP_BODY"
      exit 0
    }
    echo "  ✓ curl 成功 [HTTP $HTTP_STATUS]，字段: $JSON_PATH = $RESULT"
    echo "$RESULT"
    exit 0
  else
    echo "  ✓ curl 成功 [HTTP $HTTP_STATUS]"
    echo "$HTTP_BODY"
    exit 0
  fi
fi

# ─── Step 2: Playwright 截图降级 ──────────────────────────────────────────────
echo ""
echo "▶ [Playwright] 降级：截图分析 $URL"

# 检查 playwright 是否可用
if ! command -v npx &>/dev/null && ! command -v uv &>/dev/null; then
  echo "  ✗ 既无 npx 也无 uv，无法运行 Playwright" >&2
  echo "  提示：安装方式之一：npm install -g playwright 或 uv add playwright" >&2
  exit 1
fi

# 构造 Playwright 截图脚本
PW_SCRIPT=$(mktemp /tmp/pw_capture_XXXXXX.js)
cat > "$PW_SCRIPT" << 'PLAYWRIGHT_SCRIPT'
const { chromium } = require('playwright');
(async () => {
  const url  = process.argv[2];
  const out  = process.argv[3];
  const browser = await chromium.launch({ headless: true });
  const page    = await browser.newPage();
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.setExtraHTTPHeaders({
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
  });
  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
    // 等待主要内容渲染
    await page.waitForTimeout(2000);
    await page.screenshot({ path: out, fullPage: true });
    // 同时尝试提取页面可见文本
    const text = await page.evaluate(() => document.body.innerText);
    console.log('__TEXT_START__');
    console.log(text.substring(0, 8000));   // 限制输出大小
    console.log('__TEXT_END__');
  } finally {
    await browser.close();
  }
})();
PLAYWRIGHT_SCRIPT

PW_RESULT=""
if command -v npx &>/dev/null; then
  PW_RESULT=$(npx --yes playwright@latest node "$PW_SCRIPT" "$URL" "$SCREENSHOT_OUT" 2>/dev/null) || true
elif command -v uv &>/dev/null; then
  PW_RESULT=$(uv run --with playwright python -c "
import asyncio, sys
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_viewport_size({'width': 1440, 'height': 900})
        await page.goto('$URL', wait_until='networkidle', timeout=30000)
        await page.wait_for_timeout(2000)
        await page.screenshot(path='$SCREENSHOT_OUT', full_page=True)
        text = await page.evaluate('() => document.body.innerText')
        print('__TEXT_START__')
        print(text[:8000])
        print('__TEXT_END__')
        await browser.close()
asyncio.run(main())
" 2>/dev/null) || true
fi

rm -f "$PW_SCRIPT"

if [[ -f "$SCREENSHOT_OUT" ]]; then
  echo "  ✓ Playwright 截图保存至: $SCREENSHOT_OUT"
  echo "  → 请使用 Read 工具读取截图进行视觉分析"
  # 提取可见文本（供 Claude 直接读取）
  PAGE_TEXT=$(echo "$PW_RESULT" | sed -n '/^__TEXT_START__$/,/^__TEXT_END__$/p' | grep -v '__TEXT')
  if [[ -n "$PAGE_TEXT" ]]; then
    echo ""
    echo "── 页面可见文本摘要 ──────────────────────────────────────"
    echo "$PAGE_TEXT" | head -100
    echo "──────────────────────────────────────────────────────────"
  fi
  exit 2   # 截图成功，需视觉分析
else
  echo "  ✗ Playwright 截图失败，请手动访问: $URL" >&2
  exit 1
fi
