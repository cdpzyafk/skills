# Exchange API Impact Report
Generated: {YYYY-MM-DD HH:MM}
Exchanges checked: OKX / Binance / Bybit / GateIO
Project: {project root path}

---

## ⚠️ Breaking Changes ({N} total)

> Changes that may silently corrupt logic or cause runtime errors if not addressed.

### [{Exchange}] {YYYY-MM-DD} — {Change title}

**Summary**: {One sentence describing what changed and why it matters.}
**Deadline**: {Date the change goes live, or "Already live" / "None stated"}

| File | Line | Current usage | Required change |
|------|------|---------------|-----------------|
| `path/to/file.go` | 42 | `item["fieldName"] == "oldValue"` | Change to `"newValue"` — enum updated |
| `tools/scripts/foo.py` | 17 | `resp["deprecatedField"]` | Replace with `resp["newField"]` |

**Impact level**: High / Medium / Low
**Confidence**: Confirmed hit / Inferred (field name is common) / Not found — manual check advised

---

## 📢 Additive Changes ({N} total)

> New endpoints, fields, or parameters. No breakage, but worth considering.

### [{Exchange}] {YYYY-MM-DD} — {Change title}

**Summary**: {What was added and what it enables.}

**Relevant files**: none found — project does not yet use affected APIs
**Recommendation**: {Consider adopting `newField` for X purpose} / No action needed

---

## ✅ No Action Required ({N} entries scanned, no hits)

The following entries were scanned but produced zero matches in the codebase:

| Exchange | Date | Change | Identifiers searched |
|----------|------|--------|----------------------|
| OKX | 2026-03-10 | Delivery price window 1h→30min | `expTime`, `/api/v5/public/estimated-price` |
| Binance | 2026-03-09 | Price Range Execution Rule | `/api/v3/executionRules`, `referencePrice` |
| Bybit | 2026-03-12 | Delta Neutral Mode | `deltaEnable`, `SetDeltaNeutralMode` |

---

## 📋 Summary

| Exchange | Breaking | Additive | Files affected | Action required |
|----------|----------|----------|----------------|-----------------|
| OKX      | 0        | 0        | 0              | None            |
| Binance  | 0        | 1        | 0              | Optional review |
| Bybit    | 0        | 0        | 0              | None            |
| GateIO   | 0        | 0        | 0              | None            |
| **Total**| **0**    | **1**    | **0**          |                 |

---

## 🔍 Scan Methodology

- Script: `~/.claude/skills/check-upcoming/scripts/fetch_upcoming_changes.py`
- Search scope: `**/*.go`, `**/*.py` (excluding `.venv/`, `vendor/`, `*.pb.go`)
- Identifiers used: API endpoint paths, field names, enum values, struct/model names
- Generic identifiers (e.g. `id`, `type`) flagged as ambiguous and noted separately
