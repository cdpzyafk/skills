---
name: jira-task
description: Use when the user mentions a Jira issue key (like TRAD-83, ABC-123, PROJ-456), says "implement this ticket", "work on jira task", "pull jira issue", "根据jira任务", "看一下这个jira", or wants to analyze/implement a Jira task. ALWAYS invoke when you see a Jira-style issue key (letters-digits pattern like TRAD-83) in the user's message, even if they just paste the key with no other context.
---

# jira-task

Workflow for pulling a Jira task, understanding the codebase, designing code changes, and generating a design document.

## 全自动执行原则

**本技能全程无需用户确认，自动完成所有步骤。**

- 每个步骤完成后，**立即自动进入下一步**，不等待用户输入
- 遇到路径选择（语言、文件、方案），**自动做出最合理的判断并直接执行**，无需询问
- 遇到歧义时，选择影响最小、最保守的方案直接推进
- 只在全部步骤完成后，才向用户汇报结果

## Overview

Given a Jira issue key, you will run a fully automated pipeline:
1. Fetch the full issue from Jira (summary, description, acceptance criteria, comments)
2. Explore the codebase to locate relevant code
3. Design concrete, targeted code changes
4. Write a design document to `docs/<ISSUE-KEY>.md`
5. Auto-review with `fintech-product-manager` — check for functional and code gaps, patch the docs
6. Auto-implement with `golang-pro` (Go) or `python-pro` (Python) following the finalized design
7. Auto-simplify with `code-simplifier` — clean up the changed code without altering behavior
8. Auto-QA with `qa-expert` — verify correctness, coverage, and edge cases; fix any issues found

## Step 1: Extract the issue key

Pull the Jira issue key from the user's message. It follows the pattern `[A-Z]+-[0-9]+` (e.g., `TRAD-83`, `OPT-12`). If there are multiple keys, process each one.

## Step 2: Fetch the Jira issue

Use `mcp__atlassian__jira_get_issue` with the issue key. Capture:
- **Summary** — the one-line title
- **Description** — full requirements, background, context
- **Acceptance criteria** — what "done" looks like (often in the description or a custom field)
- **Issue type** — Bug, Story, Task, etc.
- **Priority** — helps understand urgency
- **Labels / components** — hints at which subsystem is involved
- **Comments** — may contain important clarifications or decisions

If the description references other issues, fetch those too with `mcp__atlassian__jira_get_issue`.

## Step 3: Understand the codebase

Read `CLAUDE.md` (if present) for architecture context. Then explore the code to find what needs to change.

Start with targeted searches based on keywords from the issue (symbol names, exchange names, feature names). Use `Glob` and `Grep` to locate relevant files. Read the files that are most likely to change.

Your goal is to understand:
- Which files and functions are involved
- What the current behavior is
- What the desired behavior should be (from the issue)
- What the impact/blast radius of changes would be

Do not read the entire codebase — be surgical. 3–8 focused searches are usually enough.

## Step 4: Design the changes

Think through the implementation:
- What needs to be added, modified, or removed?
- Are there edge cases or risks?
- Does this require config changes, new data structures, or new dependencies?
- What tests should be updated or added?

Be specific: name the files, functions, and the nature of each change. Don't write final code yet — this is the design phase.

## Step 5: Write the design document

Create `docs/<ISSUE-KEY>.md` in the project root. Use this structure:

```markdown
# <ISSUE-KEY>: <Summary>

## Jira Issue

- **Key**: <ISSUE-KEY>
- **Type**: <Bug/Story/Task/...>
- **Priority**: <priority>
- **Summary**: <summary>

## Requirements

<Paste or summarize the full description and acceptance criteria from Jira.>

## Codebase Analysis

### Relevant files

| File | Role |
|------|------|
| `path/to/file.go` | Brief description of why it's relevant |

### Current behavior

<Describe what the code currently does in the relevant area.>

### Gap

<What the current code doesn't do that the issue requires.>

## Design

### Changes required

For each change, describe:

#### `path/to/file.go`
- **Function/struct**: `FunctionName`
- **Change**: What needs to change and why
- **Sketch**:
  ```go
  // Brief pseudocode or key lines — not a full implementation
  ```

### Data flow / sequence (if relevant)

<A brief narrative or ASCII diagram showing how data flows through the change.>

### Edge cases and risks

- <Risk 1>
- <Risk 2>

### Tests

- <What to test and where>

## Open questions

<Any ambiguities in the requirements that should be clarified before implementation.>
```

Adapt the structure as needed — for a simple bug fix, drop sections that don't apply. For a large feature, add more detail. The goal is a document someone could use to implement the changes without needing to re-read the Jira issue or re-explore the code.

## Step 6: Review the document with the fintech-product-manager lens

写完文档后，**立即自动**调用 `fintech-product-manager` skill 对 `docs/<ISSUE-KEY>.md` 进行审查。不等待用户确认，直接执行。

The review has two angles:

### 6a. Functional completeness

From a product perspective, ask:
- Does the design cover **all** the requirements stated in the Jira issue? Check each requirement and acceptance criterion one by one.
- Are there edge cases in the **business logic** that are not addressed? (e.g., boundary conditions on rates, handling of settlement delays, missing validation rules)
- Are any **user-facing behaviors** described in the issue missing from the design? (e.g., notifications, error states, UI triggers)
- Are there **risk or compliance** implications mentioned in the issue that the design doesn't handle?

### 6b. Code completeness

From a code perspective, ask:
- Are all **call sites** accounted for? If a function changes its signature or behavior, are all callers updated?
- Are **config files or constants** that need updating listed?
- Are there **monitoring or alerting** hooks that need to be added/updated alongside the feature code?
- Are there **tests** (unit, integration) that need to change that weren't listed?
- Are there **dependent services or downstream consumers** that may be affected but weren't mentioned?

### Updating the docs

After the review, append a `## Review Notes` section to `docs/<ISSUE-KEY>.md` with the findings:

```markdown
## Review Notes

### Functional gaps found
- <gap 1 — description and suggested resolution>
- <gap 2>

### Code points missing
- <missing point 1>
- <missing point 2>

### No issues found
<State "None" here if everything checks out.>
```

If gaps were found, also update the relevant sections of the document (Requirements, Design) to incorporate the fixes — don't just list them in Review Notes and leave the rest of the docs stale.

## Step 7: Implement the changes

After the review is complete and the docs is finalized, **立即自动进入实现阶段，不等待用户确认**。

### Detect the language（自动判断，无需询问）

Scan the files listed in the "Relevant files" table of the design docs and **immediately decide**:
- `.go` files 占多数 → 直接调用 `golang-pro` skill，全程按其规范实现
- `.py` files 占多数 → 直接调用 `python-pro` skill，全程按其规范实现
- Mixed / ambiguous → 以改动最多的文件的语言为准，直接选定，继续执行

### Implement following the design

Work through every change listed in the "Changes required" section of `docs/<ISSUE-KEY>.md`. For each change:
1. Read the current file content before editing
2. Apply only what the design specifies — stay within scope
3. Keep changes minimal and focused; do not refactor surrounding code

Follow all conventions and rules from the invoked language skill (golang-pro or python-pro) — naming, error handling, concurrency patterns, type safety, etc.

After all changes are applied, update `docs/<ISSUE-KEY>.md` — add an `## Implementation` section listing each file changed and a one-line summary of what was done.

## Step 8: Simplify with code-simplifier

实现完成后，**立即自动**对 Step 7 中所有改动的文件调用 `code-simplifier` skill。不等待用户确认。

The simplifier should:
- Remove redundant logic, unnecessary abstractions, and dead code introduced by the changes
- Ensure consistency with surrounding code style and conventions
- Preserve all functionality — behavior must not change

After simplification, update the `## Implementation` section in `docs/<ISSUE-KEY>.md` to note that the code was simplified.

## Step 9: QA check with qa-expert

简化完成后，**立即自动**调用 `qa-expert` skill。不等待用户确认，直接执行 QA。QA 分两部分：

### Part A: Write test cases

For every changed file, write concrete test cases covering:
- **Happy path** — the primary use case described in the Jira requirements
- **Edge cases** — boundary conditions identified in the design docs
- **Error paths** — invalid inputs, missing data, error returns
- **Regression** — existing behavior that must not change

Write the tests directly into the appropriate test files (e.g., `*_test.go` for Go, `test_*.py` for Python). Follow the same language conventions as the implementation (golang-pro or python-pro rules apply here too). Do not just describe tests — write real, runnable test code.

### Part B: Run the tests and make them pass

Run the full test suite:
- **Go**: `go test ./...`
- **Python**: `pytest` or the project's test runner

If any tests fail:
1. Diagnose the failure — is it a test bug or an implementation bug?
2. Fix the root cause (implementation or test, whichever is wrong)
3. Re-run until all tests pass
4. Do not skip, comment out, or weaken assertions to force a pass

Keep iterating until `go test ./...` (or equivalent) exits with code 0.

### Part C: Update the docs

Append a `## QA Report` section to `docs/<ISSUE-KEY>.md`. This section must include the full test cases — not just a summary table, but the actual test code — so the document is a self-contained record of what was tested and why.

```markdown
## QA Report

### Test cases

For each test file touched, list every test case written with its full source:

#### `path/to/file_test.go` (or `test_file.py`)

**`TestFunctionName_happyPath`** — normal flow, <what it verifies>
```go
func TestFunctionName_happyPath(t *testing.T) {
    // full test code here
}
```

**`TestFunctionName_edgeCase`** — <edge case description>
```go
func TestFunctionName_edgeCase(t *testing.T) {
    // full test code here
}
```

*(repeat for every test case written)*

### Issues found and fixed

- <issue — file:line, description, fix applied>

### Test run result

```
<paste the final test runner output showing all tests pass>
```

### Verdict

PASS
```

The verdict must be **PASS** before the task is considered done. Do not declare completion until the test run output confirms it.

## After everything is complete

Tell the user:
- Where the docs was written (`docs/<ISSUE-KEY>.md`)
- A one-paragraph summary of the key design decisions
- What the fintech-product-manager review found (gaps fixed, or "review passed")
- What was implemented (files changed)
- QA verdict — PASS with test output confirming all tests green
- Any open questions that remain
