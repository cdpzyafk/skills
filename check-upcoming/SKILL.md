---
name: check-upcoming
description: >
  Use whenever the user wants to audit exchange API changelog updates against the current codebase.
  Triggers on: "check upcoming changes", "check changelog", "API有没有更新", "交易所有没有改接口",
  "看下最新的API变更", "check if exchange changes affect our code", "有没有breaking change",
  "OKX/Binance/Bybit/GateIO/KuCoin有没有更新", "run check-upcoming", or any request to compare
  exchange API changes with the project. ALWAYS invoke when the user asks whether exchange
  API updates require code modifications, even if phrased as a question like "do we need to
  update anything?" or "need to change code for the new API?".
---

# check-upcoming

Fetch exchange API changelogs, cross-reference against the codebase, and produce a structured
impact report telling you exactly which files need changing and why.

## Overview

Three phases:
1. **Fetch** — run `fetch_upcoming_changes.py` to pull OKX / Binance / Bybit / GateIO / KuCoin changelogs
2. **Scan** — extract key identifiers from each changelog entry; grep the codebase for them
3. **Report** — output a structured modification report (file → current usage → required change)

---

## Phase 1 — Fetch Changelogs

The fetch script is bundled with this skill at `scripts/fetch_upcoming_changes.py`
(relative to this SKILL.md's directory). Run it from anywhere — it has no project dependency.

```bash
SKILL_DIR=~/.claude/skills/check-upcoming

bash $SKILL_DIR/scripts/run_fetch.sh              # all exchanges
bash $SKILL_DIR/scripts/run_fetch.sh okx binance  # subset
bash $SKILL_DIR/scripts/run_fetch.sh gateio kucoin
```

The wrapper script (`run_fetch.sh`) uses `uv run` to automatically provide playwright,
requests, and beautifulsoup4 — no manual dependency installation needed.
If `uv` is not available, it falls back to calling `python3` directly (requires deps installed).

Script paths:
- `~/.claude/skills/check-upcoming/scripts/run_fetch.sh` — entrypoint (use this)
- `~/.claude/skills/check-upcoming/scripts/fetch_upcoming_changes.py` — underlying script

The script prints formatted markdown to stdout. Capture the full output — it is the raw material
for Phase 2.

**Supported exchanges:** `okx` / `binance` / `bybit` / `gateio` / `kucoin`

**GateIO and KuCoin** require a real browser (Cloudflare WAF + JS rendering). The script uses
Playwright automatically. If playwright is not installed, two options:
- Pass `--auto-install` and the script installs it on the fly
- Or install once manually: `pip install playwright && playwright install chromium`

Dependencies: handled automatically by `run_fetch.sh` via `uv run`. No manual install needed.

---

## Phase 2 — Scan the Codebase

### 2a. Triage changelog entries by severity

For each entry in the fetched output, classify it:

| Severity | Criteria | Action |
|----------|----------|--------|
| **BREAKING** | field removed/renamed, type changed, behavior changed, enum value changed, endpoint deprecated with deadline | Must fix before deadline |
| **ADDITIVE** | new field added, new endpoint, new optional parameter | Check if we should use it |
| **INFO** | documentation clarification, maintenance notice | No code change needed |

Focus your scan effort on BREAKING first, then ADDITIVE. Skip INFO entries entirely.

### 2b. Extract identifiers

For each BREAKING / ADDITIVE entry, extract the concrete identifiers that would appear in code:

- **API endpoint paths**: `/api/v5/public/instruments`, `/fapi/v1/historicalTrades`
- **Field / parameter names**: `instCategory`, `expTime`, `bidPx`, `selfTradePreventionMode`
- **Enum values / constants**: `"EXPIRED_IN_MATCH"`, `"commodity"`
- **Struct / model names**: `BatchOrder`, `UnifiedAccount`
- **WebSocket channel names**: `mark-price`, `tickers`

Be specific — use the exact string that would appear in source code (JSON tags, string literals,
struct field names).

### 2c. Search the project

Search the codebase for each identifier. **Exclude** generated files, vendored dependencies,
and the fetch script itself:

```bash
# Paths to search (adjust to project root)
grep -rn "IDENTIFIER" \
  --include="*.go" --include="*.py" \
  --exclude-dir=".venv" \
  --exclude-dir="vendor" \
  --exclude-dir=".claude" \
  --exclude="*.pb.go" \
  --exclude="fetch_upcoming_changes.py" \
  .
```

For each grep hit, note:
- File path (relative to project root)
- Line number
- The surrounding context (the line itself, plus 1-2 lines around it for clarity)
- How the identifier is used: reading a field, passing a parameter, matching an enum, etc.

---

## Phase 3 — Impact Report

### 语言规则（严格执行）

报告**只能使用中文或英文**。Changelog 中出现的其他语言（韩文、日文等）翻译成英文后再输出。

表格单元格中常用词的正确写法：

| 含义 | 正确（中文） | 正确（英文） | ❌ 错误示例 |
|------|------------|------------|-----------|
| 无/没有 | 无 | None | ~~없음~~ |
| 合计 | 合计 | Total | ~~합계~~ |
| 无影响 | 无影响 | No impact | ~~영향 없음~~ |
| 无需操作 | 无需操作 | No action | ~~조치 불필요~~ |

选定一种语言后，整份报告保持一致；不要同一份报告内中英混排表格。

---

Read `references/report-template.md` for the complete template before writing the report.
The four required sections are:

1. **⚠️ Breaking Changes** — table per entry: File | Line | Current usage | Required change + Deadline + Impact level
2. **📢 Additive Changes** — relevant files found + recommendation
3. **✅ No Action Required** — table of scanned-but-no-hit entries with identifiers searched; include a "结论/Conclusion" column explaining *why* there is no impact (e.g., "endpoint not used", "field commented out")
4. **📋 Summary** — one row per exchange: Breaking | Additive | Files affected | Action required

---

## Tips for good analysis

**Finding real impact vs noise:**
- A field appearing in a comment or log string is not a breaking dependency — note it but don't flag it as critical.
- A field used in a struct tag (`json:"instCategory"`) or a map lookup (`item["instCategory"]`) IS a dependency.
- Type changes (string → int) are always breaking if the field is used.
- New enum values are only breaking if the code uses exhaustive switches or explicit equality checks.

**This project's structure to know:**
- Go exchange wrappers live in `serviceapi/<exchange>/` (e.g. `serviceapi/okex/`, `serviceapi/binance/`, `serviceapi/gateio/`, `serviceapi/kucoin/`, `serviceapi/bybit/`)
- Generated protobuf files (`*.pb.go`) — skip these, they won't contain exchange API field names directly
- The `vendor/` directory — always exclude from grep
- The `.claude/worktrees/` directory — always exclude, it's stale branch copies

**When nothing is found:**
If grep returns no results for a changelog entry's identifiers, say so explicitly in the
"No Action Required" section. Don't omit entries — the user needs to know you checked.

**Ambiguous identifiers:**
Some field names like `id`, `type`, or `status` are too generic to grep usefully. For these,
search for the combination of the endpoint path + field name, or note that the identifier is
too generic for automated search and suggest manual review of the relevant service file.
