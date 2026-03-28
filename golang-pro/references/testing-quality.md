# Testing and Quality

Go testing patterns and code quality tools. Load this when writing tests, setting up linting, or doing code review.

---

## Writing Useful Tests

### When
Writing any test function — unit, integration, or benchmark.

### What
Tests must be self-diagnosing. A failure message should tell you exactly what went wrong without reading the test source.

### How

**Failure message format**: `YourFunc(%v) = %v, want %v`

```go
// Good: includes function name, inputs, got, want
if got := Add(2, 3); got != 5 {
    t.Errorf("Add(2, 3) = %d, want %d", got, 5)
}

// Bad: missing context
if got := Add(2, 3); got != 5 {
    t.Errorf("got %d, want %d", got, 5)
}
```

**Got before want**: always print actual before expected.

**Use `cmp.Diff` for structs and slices**:

```go
want := &Doc{Type: "blogPost", Authors: []string{"alice"}}
if diff := cmp.Diff(want, got); diff != "" {
    t.Errorf("AddPost() mismatch (-want +got):\n%s", diff)
}
```

**`t.Error` vs `t.Fatal`**:
- `t.Error`: report failure, continue testing (preferred — surfaces all failures at once)
- `t.Fatal`: stop immediately when continuation is meaningless (e.g., after setup failure)
- **Never call `t.Fatal` from a goroutine** — use `t.Error` + return

**No assertion libraries**: standard `cmp` + `t.Errorf` gives better failure messages.

### 预设失败策略
- Test failure message is cryptic → add the function name and inputs to the message
- `t.Fatal` everywhere → switch to `t.Error` unless subsequent assertions would be meaningless
- Testing a goroutine → communicate back via channel, check with `t.Error`

---

## Table-Driven Tests

### When
Multiple test cases share identical logic with different inputs and expected outputs.

### What
Factor out repeated test logic into a table of cases.

### How

```go
func TestCompare(t *testing.T) {
    tests := []struct {
        name    string
        a, b    string
        want    int
    }{
        {name: "equal", a: "abc", b: "abc", want: 0},
        {name: "a_before_b", a: "a", b: "b", want: -1},
        {name: "empty", a: "", b: "", want: 0},
    }
    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            got := Compare(tt.a, tt.b)
            if got != tt.want {
                t.Errorf("Compare(%q, %q) = %v, want %v", tt.a, tt.b, got, tt.want)
            }
        })
    }
}
```

**Table tests work best when:**
- All cases run identical logic (no conditional assertions)
- No conditional mock setup based on test fields
- Setup is the same for all cases

**When to use separate test functions instead**: complex setup, conditional mocking, multiple execution branches. Conditional fields like `shouldCallX bool` are a red flag.

**Parallel subtests**: safe in Go 1.22+. For 1.21 and earlier, add `tt := tt` inside the loop before calling `t.Parallel()`.

### 预设失败策略
- Table test has `shouldCallX bool` fields → split into separate focused test functions
- Test cases are growing complex → some cases need separate test functions; that's fine
- Row identified by index ("Case #3") → always use `t.Run(tt.name, ...)` with a descriptive name

---

## Test Helpers

### When
Multiple tests share setup logic (opening files, creating databases, building structs).

### What
Extract into a helper function that calls `t.Helper()` so failures point to the caller.

### How

```go
// Good: complete test helper pattern
func mustLoadTestData(t *testing.T, filename string) []byte {
    t.Helper() // failures point to the caller line
    data, err := os.ReadFile(filename)
    if err != nil {
        t.Fatalf("Setup: could not read %s: %v", filename, err)
    }
    return data
}

func setupTestDB(t *testing.T) *sql.DB {
    t.Helper()
    db, err := sql.Open("sqlite3", ":memory:")
    if err != nil {
        t.Fatalf("Could not open database: %v", err)
    }
    t.Cleanup(func() { db.Close() }) // use Cleanup, not defer
    return db
}
```

**Key rules**:
- Call `t.Helper()` first
- Use `t.Fatal` for setup failures (the test can't meaningfully continue)
- Use `t.Cleanup()` for teardown — it runs even if `t.Fatal` is called later

### 预设失败策略
- Error points to helper line instead of caller → add `t.Helper()` at the top of the helper
- Cleanup not running → switch from `defer` to `t.Cleanup(func() { ... })`

---

## Test Doubles

### When
A dependency is too slow, unreliable, or complex to use directly in tests.

### What
Use consistent naming and packaging conventions for stubs, fakes, mocks, and spies.

### How

**Package naming**: append `test` to the production package — `creditcardtest`, not `mocks`.

```go
// In package creditcardtest:

// Single double — use the simple type name
type Stub struct{}
func (Stub) Charge(*creditcard.Card, money.Money) error { return nil }

// Multiple behaviors — name by behavior
type AlwaysCharges struct{}
type AlwaysDeclines struct{}
```

**Local variable naming**: prefix with type to distinguish from production code (`spyCC`, not `cc`).

**Test error semantics** — check error identity, not string content:

```go
// Good: test the semantic meaning
if !errors.Is(err, ErrInvalidInput) {
    t.Errorf("got %v, want ErrInvalidInput", err)
}

// Bad: brittle — message can change
if err.Error() != "invalid input" { ... }
```

### 预设失败策略
- Mock library is complex/slow → write a hand-written struct implementing the interface; it's faster to read, easier to debug, and has no dependency
- Testing internal behavior through mocks → test via observable outputs instead; mocks for external dependencies only

---

## Code Review Checklist

### When
Reviewing Go code or self-reviewing before submitting a PR.

### What
Systematic check against common Go style issues.

### How

**Formatting**: `gofmt`/`goimports` applied.

**Documentation**: all exported names have doc comments; comments are complete sentences.

**Error handling**:
- [ ] No discarded errors with `_`
- [ ] Error strings are lowercase, no trailing punctuation
- [ ] No magic return values (`-1`, `""`, `nil`) to signal errors
- [ ] Error handling is first, normal path unindented

**Naming**:
- [ ] MixedCaps — no underscores except in test names
- [ ] Initialisms consistent: `URL`/`url`, `ID`/`id`
- [ ] Receiver names: 1-2 letters, consistent across methods

**Concurrency**:
- [ ] Goroutine lifetimes are clear
- [ ] Context is first parameter
- [ ] No goroutines stored/returned from constructors

**Interfaces**:
- [ ] Interfaces defined in consumer package
- [ ] No premature interface extraction
- [ ] Receiver type consistent (all pointer or all value)

**Data**:
- [ ] `var t []string` preferred over `t := []string{}` for empty slices
- [ ] No struct copies where methods are on `*T`

**Security**:
- [ ] `crypto/rand` for key generation, never `math/rand`
- [ ] No panic in library code

**Quick commands**:

```bash
goimports -w .
golangci-lint run
go vet ./...
go test -race ./...
```

### 预设失败策略
- Lint catches a false positive → suppress with a comment explaining why; don't disable the linter globally
- Review feels too strict for a small PR → apply the checklist selectively; naming and error handling always apply

---

## Linting Setup

### When
Setting up a new Go project or adding CI/CD quality gates.

### What
Consistent linting across the codebase catches common issues and enforces quality.

### How

**Minimum linter set** (via golangci-lint):

| Linter | Purpose |
|--------|---------|
| `errcheck` | Ensure errors are handled |
| `goimports` | Format + manage imports |
| `revive` | Style mistakes (replaces deprecated `golint`) |
| `govet` | Common code mistakes |
| `staticcheck` | Static analysis |

**`.golangci.yml`**:

```yaml
linters:
  enable:
    - errcheck
    - goimports
    - revive
    - govet
    - staticcheck

linters-settings:
  goimports:
    local-prefixes: github.com/your-org/your-repo
  revive:
    rules:
      - name: blank-imports
      - name: context-as-argument
      - name: error-return
      - name: error-strings
      - name: exported

run:
  timeout: 5m
```

```bash
go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest
golangci-lint run
```

### 预设失败策略
- Too many lint violations on existing codebase → enable linters one at a time; fix the most impactful first (`errcheck`, `govet`)
- CI too slow with linting → use `golangci-lint run --new-from-rev=HEAD~1` to lint only changed files
