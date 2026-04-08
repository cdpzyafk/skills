# Quick Sanity Checklist

Run through all items before writing the review output. Items that fail become findings if not already captured in the detailed scans.

| # | Check | Notes |
|---|-------|-------|
| ☐ | **代码可编译、可运行** | No obvious syntax errors, missing imports, or type mismatches |
| ☐ | **命名清晰，无无意义变量** | No `tmp`, `data2`, `x2`, single-letter names outside tight loops |
| ☐ | **函数单一职责，不过长** | Functions have one reason to change; flag >40 lines as a smell |
| ☐ | **错误处理完整，无空catch** | No swallowed exceptions; every error path produces signal |
| ☐ | **外部输入校验** | All user/API/DB inputs validated at system boundary |
| ☐ | **无硬编码密钥、路径** | No API keys, tokens, or env-specific absolute paths in code |
| ☐ | **无循环内IO** | No DB queries, HTTP calls, or file ops inside loops |
| ☐ | **资源正确释放** | Connections, file handles, goroutines/threads have clear cleanup |
| ☐ | **无并发不安全** | Shared state accesses are synchronized; no check-then-act races |
| ☐ | **无Claude编造API/幻觉** | Every method/function called actually exists in the library at the version in use — grep or check docs for unfamiliar APIs before trusting them |
| ☐ | **关键逻辑有单测** | Happy path + at least one error path covered for critical logic |
| ☐ | **符合团队风格规范** | Formatting, naming conventions, import order match the project |

> **"无Claude编造API/幻觉"** is the most failure-prone check for AI-generated code. If you see an unfamiliar method chained on a known library type, verify it exists — don't assume.
