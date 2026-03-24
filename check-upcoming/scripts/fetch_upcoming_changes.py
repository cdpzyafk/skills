#!/usr/bin/env python3
"""
获取 OKX / Binance / Bybit / GateIO / KuCoin 现货&合约&期权接口文档更新日志

用法:
    python fetch_upcoming_changes.py                          # 全部交易所
    python fetch_upcoming_changes.py okx bybit                # 指定交易所（不区分大小写）
    python fetch_upcoming_changes.py --auto-install           # 全部，playwright 未安装时自动安装
    python fetch_upcoming_changes.py gateio --auto-install    # 指定 + 自动安装
"""

import re
import sys
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable

import requests
from bs4 import BeautifulSoup, NavigableString, Tag
from urllib3.exceptions import InsecureRequestWarning

warnings.filterwarnings("ignore", category=InsecureRequestWarning)

REQUEST_TIMEOUT = 30
PLAYWRIGHT_TIMEOUT = 60_000  # ms
MAX_LINES = 120  # 每个 section 最多输出行数

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# 页面导航噪音，精确匹配后忽略整行
_NOISE_LINES = {
    "on this page",
    "table of contents",
    "edit this page",
    "edit page",
    "previous",
    "next",
    "python",
    "shell",
    "opens new window",
}

# 段落级别的噪音前缀（以这些词开头的行直接丢弃）
_NOISE_PREFIXES = (
    "scroll down for code",
    "select a language",
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class ChangelogResult:
    exchange: str
    product: str
    url: str
    content: str = ""
    error: str = ""


# ---------------------------------------------------------------------------
# Playwright helpers
# ---------------------------------------------------------------------------


def ensure_playwright(auto_install: bool = False) -> None:
    """确保 playwright 可用。auto_install=True 时自动安装缺失依赖。"""
    try:
        import playwright  # noqa: F401
        return
    except ImportError:
        pass

    if not auto_install:
        raise RuntimeError(
            "playwright 未安装，请执行以下命令后重试:\n"
            "  pip install playwright && playwright install chromium\n"
            "或在命令行加上 --auto-install 参数自动安装。"
        )

    print("[playwright] 未安装，正在自动安装...", file=sys.stderr)
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "playwright", "-q"], check=True)
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    print("[playwright] 安装完成。", file=sys.stderr)


def fetch_html_playwright(url: str, *, wait_selector: str | None = None) -> str:
    """使用 Playwright 无头浏览器抓取，适用于 Cloudflare 等 WAF 保护的页面。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError(
            "playwright 未安装，请执行: pip install playwright && playwright install chromium\n"
            "或使用 --auto-install 参数自动安装。"
        )

    anchor: str | None = None
    if "#" in url:
        _, anchor = url.split("#", 1)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=HEADERS["User-Agent"],
            locale="zh-CN",
            extra_http_headers={"Accept-Language": HEADERS["Accept-Language"]},
        )
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=PLAYWRIGHT_TIMEOUT)

        # 等待指定 selector（如果提供）
        if wait_selector:
            try:
                page.wait_for_selector(wait_selector, timeout=PLAYWRIGHT_TIMEOUT)
            except Exception:
                pass
        elif anchor:
            try:
                page.wait_for_selector(f"#{anchor}", timeout=PLAYWRIGHT_TIMEOUT)
            except Exception:
                pass

        try:
            page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass

        html = page.content()
        browser.close()
    return html


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, verify=False)
    resp.raise_for_status()
    return resp.text


# ---------------------------------------------------------------------------
# HTML → 可读文本渲染器
# ---------------------------------------------------------------------------

_SKIP_TAGS = {"script", "style", "nav", "button", "svg", "img", "noscript", "iframe"}
_BLOCK_TAGS = {"div", "section", "article", "main", "aside", "header", "footer", "form", "blockquote"}


def html_to_text(node: Tag | BeautifulSoup) -> str:
    """将 HTML 节点树渲染为结构化可读文本（Markdown-like）。"""

    def render(n: object) -> str:
        if isinstance(n, NavigableString):
            return str(n)
        if not isinstance(n, Tag):
            return ""
        if n.name in _SKIP_TAGS:
            return ""

        inner = "".join(render(c) for c in n.children)

        if n.name == "h1":
            return f"\n\n## {_strip_anchor(inner)}\n"
        if n.name == "h2":
            return f"\n\n### {_strip_anchor(inner)}\n"
        if n.name in ("h3", "h4", "h5", "h6"):
            return f"\n\n#### {_strip_anchor(inner)}\n"
        if n.name == "li":
            return f"- {inner.strip()}\n"
        if n.name in ("ul", "ol"):
            return "\n" + inner + "\n"
        if n.name == "p":
            t = inner.strip()
            return f"\n{t}\n" if t else ""
        if n.name == "code":
            t = inner.strip()
            return f"`{t}`" if t else ""
        if n.name in ("strong", "b"):
            t = inner.strip()
            return f"**{t}**" if t else ""
        if n.name in ("em", "i"):
            t = inner.strip()
            return f"*{t}*" if t else ""
        if n.name == "a":
            return inner.strip()
        if n.name == "br":
            return "\n"
        if n.name == "hr":
            return "\n---\n"
        if n.name in _BLOCK_TAGS:
            t = inner.strip()
            return f"\n{t}\n" if t else ""
        return inner

    return render(node)


def _strip_anchor(text: str) -> str:
    """去掉标题中多余的锚点 # 符号，例如 '#Changelog' → 'Changelog'。"""
    return text.strip().lstrip("#").strip()


def post_clean(text: str) -> str:
    """去除零宽字符、页面导航噪音，收紧多余空行。"""
    for ch in ("\u200b", "\u200c", "\u200d", "\ufeff"):
        text = text.replace(ch, "")

    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        low = stripped.lower()

        if low in _NOISE_LINES:
            continue
        if any(low.startswith(p) for p in _NOISE_PREFIXES):
            continue
        if stripped == "#":
            continue

        lines.append(line)

    result = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    return result.strip()


def clean_lines(text: str, limit: int = MAX_LINES) -> list[str]:
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    return lines[:limit]


# ---------------------------------------------------------------------------
# DOM 工具
# ---------------------------------------------------------------------------


def find_section_siblings(
    soup: BeautifulSoup,
    heading_id: str | None = None,
    heading_text_re: str | None = None,
    stop_tags: tuple[str, ...] = ("h1", "h2"),
) -> list[Tag]:
    """找到目标标题，返回其后、遇到 stop_tags 前的所有 Tag 兄弟节点列表。"""
    heading: Tag | None = None

    if heading_id:
        heading = soup.find(id=heading_id)  # type: ignore[assignment]

    if heading is None and heading_text_re:
        pattern = re.compile(heading_text_re, re.I)
        for tag in soup.find_all(re.compile(r"^h[1-4]$")):
            if pattern.search(tag.get_text(strip=True)):
                heading = tag
                break

    if heading is None:
        return []

    siblings: list[Tag] = []
    for node in heading.next_siblings:
        if not isinstance(node, Tag):
            continue
        if node.name in stop_tags:
            break
        siblings.append(node)

    return siblings


# ---------------------------------------------------------------------------
# OKX parser
# https://www.okx.com/docs-v5/log_zh/
# ---------------------------------------------------------------------------


def parse_okx(html: str, *, section: str = "upcoming-changes") -> str:
    soup = BeautifulSoup(html, "html.parser")

    siblings = find_section_siblings(
        soup,
        heading_id=section,
        heading_text_re=r"upcoming.change",
        stop_tags=("h1", "h2"),
    )
    if siblings:
        return "\n".join(html_to_text(s) for s in siblings)

    main = soup.find("div", class_=re.compile(r"content|doc|markdown", re.I)) or soup
    return html_to_text(main)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Binance parser
# https://developers.binance.com/docs/binance-spot-api-docs/CHANGELOG
# ---------------------------------------------------------------------------


def parse_binance(html: str, **_: object) -> str:
    soup = BeautifulSoup(html, "html.parser")

    article = soup.find("article") or soup.find("main")
    if article:
        return html_to_text(article)  # type: ignore[arg-type]

    content = soup.find(id="content") or soup.find(class_=re.compile(r"^content$", re.I))
    if content:
        return html_to_text(content)  # type: ignore[arg-type]

    return html_to_text(soup)


# ---------------------------------------------------------------------------
# Bybit parser
# https://bybit-exchange.github.io/docs/changelog/v5
# ---------------------------------------------------------------------------


def parse_bybit(html: str, **_: object) -> str:
    soup = BeautifulSoup(html, "html.parser")

    article = soup.find("article") or soup.find("main")
    if article:
        return html_to_text(article)  # type: ignore[arg-type]

    return html_to_text(soup)


# ---------------------------------------------------------------------------
# GateIO parser
# https://www.gate.com/docs/developers/apiv4/en/#changelog
# ---------------------------------------------------------------------------


def parse_gateio(html: str, **_: object) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # GateIO 文档结构（vuepress-like）：
    #   div.content-block
    #     div.content-block__heading  ← 含 h1#changelog
    #     div.content-block__body     ← 实际 changelog 内容
    heading = soup.find(id="changelog")
    if heading:
        block = heading.parent.parent  # content-block__heading → content-block
        body = block.find(class_="content-block__body") if block else None
        if body:
            return html_to_text(body)  # type: ignore[arg-type]

    # 兜底：找主体内容区
    main = (
        soup.find("div", class_=re.compile(r"content|markdown", re.I))
        or soup.find("main")
        or soup
    )
    return html_to_text(main)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# KuCoin parser
# https://www.kucoin.com/docs-new/change-log
# ---------------------------------------------------------------------------


def parse_kucoin(html: str, **_: object) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # KuCoin 新版文档（ReadMe-style）：主体内容在 <main> 下
    # Change Log 标题后跟日期段落和列表
    for tag, attrs in [
        ("main", {}),
        ("div", {"role": "main"}),
        ("article", {}),
        ("div", {"class": re.compile(r"content|markdown|changelog", re.I)}),
    ]:
        el = soup.find(tag, attrs)
        if el:
            text = html_to_text(el)  # type: ignore[arg-type]
            if len(text.strip()) > 200:  # 确保找到了实质内容
                return text

    return html_to_text(soup)


# ---------------------------------------------------------------------------
# Source catalogue
# ---------------------------------------------------------------------------

ParserFn = Callable[..., str]


@dataclass
class Source:
    exchange: str
    product: str
    url: str
    parser: ParserFn
    kwargs: dict = field(default_factory=dict)
    use_playwright: bool = False
    playwright_wait_selector: str | None = None


SOURCES: list[Source] = [
    # OKX
    Source(
        exchange="OKX",
        product="通用 Changelog",
        url="https://www.okx.com/docs-v5/log_zh/",
        parser=parse_okx,
        kwargs={"section": "upcoming-changes"},
    ),
    # Binance
    Source(
        exchange="Binance",
        product="现货 CHANGELOG",
        url="https://developers.binance.com/docs/binance-spot-api-docs/CHANGELOG",
        parser=parse_binance,
    ),
    Source(
        exchange="Binance",
        product="衍生品 CHANGELOG（合约&期权）",
        url="https://developers.binance.com/docs/derivatives/change-log",
        parser=parse_binance,
    ),
    # Bybit — 统一单页 changelog
    Source(
        exchange="Bybit",
        product="V5 全品种 Changelog",
        url="https://bybit-exchange.github.io/docs/changelog/v5",
        parser=parse_bybit,
    ),
    # GateIO — Cloudflare WAF 屏蔽非浏览器请求，使用 Playwright 无头浏览器
    Source(
        exchange="GateIO",
        product="现货&合约 Changelog",
        url="https://www.gate.com/docs/developers/apiv4/en/#changelog",
        parser=parse_gateio,
        use_playwright=True,
        playwright_wait_selector="#changelog",
    ),
    # KuCoin — JS 渲染文档，使用 Playwright
    Source(
        exchange="KuCoin",
        product="统一 Change Log",
        url="https://www.kucoin.com/docs-new/change-log",
        parser=parse_kucoin,
        use_playwright=True,
        playwright_wait_selector="main",
    ),
]


# ---------------------------------------------------------------------------
# Fetch & display
# ---------------------------------------------------------------------------


def fetch_one(source: Source) -> ChangelogResult:
    result = ChangelogResult(
        exchange=source.exchange,
        product=source.product,
        url=source.url,
    )
    try:
        if source.use_playwright:
            html = fetch_html_playwright(
                source.url,
                wait_selector=source.playwright_wait_selector,
            )
        else:
            html = fetch_html(source.url)
        raw = source.parser(html, **source.kwargs)
        result.content = post_clean(raw)
    except Exception as exc:
        result.error = str(exc)
    return result


def print_result(r: ChangelogResult) -> None:
    sep = "=" * 72
    print(f"\n{sep}")
    print(f"  {r.exchange}  |  {r.product}")
    print(f"  {r.url}")
    print(sep)
    if r.error:
        print(f"[ERROR] {r.error}", file=sys.stderr)
        print(f"[ERROR] 获取失败，请手动访问: {r.url}")
        return
    if not r.content.strip():
        print("(无内容，页面可能需要 JavaScript 渲染，请手动访问上方链接)")
        return
    for line in clean_lines(r.content):
        print(line)


def parse_args(argv: list[str]) -> tuple[list[str], bool]:
    """解析命令行：提取 --auto-install 标志，剩余为交易所名。"""
    auto_install = "--auto-install" in argv
    exchanges = [a for a in argv if not a.startswith("--")]
    return exchanges, auto_install


def filter_sources(exchanges: list[str]) -> list[Source]:
    if not exchanges:
        return SOURCES
    targets = {e.lower() for e in exchanges}
    return [s for s in SOURCES if s.exchange.lower() in targets]


def main() -> None:
    exchange_args, auto_install = parse_args(sys.argv[1:])
    sources = filter_sources(exchange_args)

    if not sources:
        known = sorted({s.exchange.lower() for s in SOURCES})
        print(f"未知交易所: {exchange_args}，可选: {' / '.join(known)}", file=sys.stderr)
        sys.exit(1)

    # 如果有需要 playwright 的 source，提前检查/安装
    needs_playwright = any(s.use_playwright for s in sources)
    if needs_playwright:
        try:
            ensure_playwright(auto_install=auto_install)
        except RuntimeError as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            # 继续运行，playwright 依赖的 source 会在 fetch_one 内捕获异常并报错

    print(f"正在并发获取 {len(sources)} 个文档页面...", file=sys.stderr)

    results: list[ChangelogResult] = [None] * len(sources)  # type: ignore[list-item]

    with ThreadPoolExecutor(max_workers=6) as pool:
        future_to_idx = {pool.submit(fetch_one, s): i for i, s in enumerate(sources)}
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            results[idx] = future.result()
            print(
                f"  [done] {results[idx].exchange} {results[idx].product}",
                file=sys.stderr,
            )

    for r in results:
        print_result(r)

    print()


if __name__ == "__main__":
    main()
