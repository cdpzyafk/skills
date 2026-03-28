# Error Handling and Control Flow

Comprehensive Go error patterns from Google and Uber style guides. Load this when writing, wrapping, returning, or handling errors — or when structuring conditionals, loops, and early returns.

---

## Returning Errors

### When
Any function that can fail. This is virtually every function doing I/O, parsing, or computation.

### What
Signal failure via the `error` interface as the last return value.

### How

```go
// Good: error is last return value
func GoodLookup() (*Result, error) {
    if err != nil {
        return nil, err
    }
    return res, nil
}

// Bad: concrete error type can cause subtle nil-interface bugs
func Bad() *os.PathError { ... }
```

When returning an error, other return values are treated as unspecified unless explicitly documented. Typically they should be zero values.

### 预设失败策略
- Should I return a partial result with an error? → Document it explicitly; otherwise return zero value + error
- Should I return `nil` or `error` for "not found"? → Use `(value, bool)` for optional lookups, `error` for unexpected failures

---

## Error Strings

### When
Writing `errors.New(...)` or `fmt.Errorf(...)`.

### What
Error strings must be lowercase, no trailing punctuation — they're often embedded in larger messages.

### How

```go
// Good
return fmt.Errorf("something bad happened")

// Bad: capitalized, punctuated
return fmt.Errorf("Something bad happened.")
```

Exception: proper nouns, exported names, acronyms may be capitalized.

### 预设失败策略
- User-visible messages (logs, API responses) → capitalize freely
- Package-level constant errors → always lowercase

---

## Error Wrapping: %v vs %w

### When
Adding context to an error before returning it up the call stack.

### What
Choose between obscuring the error chain (`%v`) or preserving it for `errors.Is`/`errors.As` (`%w`).

### How

| Use `%w` when... | Use `%v` when... |
|------------------|------------------|
| Caller needs to inspect error type | At system boundaries (HTTP handlers, main) |
| Preserving error chain for `errors.Is` | Logging — callers shouldn't inspect it |
| Internal function calls | Hiding internal implementation details |

```go
// Good: wrap with %w to preserve chain
return fmt.Errorf("parse config: %w", err)

// Good: use %v at system boundary
log.Printf("operation failed: %v", err)
```

**Placement**: `%w` always at the end: `"context message: %w"`.

**Add context callers don't have**: don't duplicate info already in the error.

```go
// Bad: duplicates error's own context
return fmt.Errorf("error: %w", err)

// Good: adds the "what were we doing"
return fmt.Errorf("load user %q: %w", userID, err)
```

If annotation adds nothing, just `return err`.

### 预设失败策略
- Error wrapping chain getting noisy → at service/handler boundary, log with `%v` and stop propagating
- Error has no context to add → `return err` directly

---

## Error Types: Choosing the Right Structure

### When
Callers need to programmatically distinguish between different failure conditions.

### What
Match error type to caller needs and message variability.

### How

| Caller needs to match? | Message type | Use |
|------------------------|--------------|-----|
| No | static | `errors.New("message")` |
| No | dynamic | `fmt.Errorf("msg: %v", val)` |
| Yes | static | `var ErrFoo = errors.New("...")` |
| Yes | dynamic | custom `error` type |

**Sentinel errors** (package-level, always `Err` prefix):

```go
var ErrInvalidInput = errors.New("invalid input")

// Check with errors.Is, never string comparison
if errors.Is(err, ErrInvalidInput) { ... }
```

**Custom error type** (when context is needed):

```go
type ValidationError struct {
    Field   string
    Message string
}

func (e *ValidationError) Error() string {
    return fmt.Sprintf("validation failed on %s: %s", e.Field, e.Message)
}

// Check with errors.As
var ve *ValidationError
if errors.As(err, &ve) {
    // ve.Field is available
}
```

### 预设失败策略
- Error type creep (too many types) → prefer sentinel errors; use custom types only when fields are needed
- Returning concrete error from exported function → always return `error` interface to avoid nil-interface bugs

---

## Handle Errors Once

### When
Receiving an error from a function call.

### What
Choose ONE response: return, log+degrade, or match+handle. Never log AND return.

### How

```go
// Bad: logs AND returns — causes duplicate logging up the stack
u, err := getUser(id)
if err != nil {
    log.Printf("Could not get user %q: %v", id, err)
    return err  // callers will log this too
}

// Good: wrap and return — let caller decide
u, err := getUser(id)
if err != nil {
    return fmt.Errorf("get user %q: %w", id, err)
}

// Good: log and degrade — non-critical failure
if err := emitMetrics(); err != nil {
    log.Printf("Could not emit metrics: %v", err)
    // continue execution
}

// Good: match specific, return others
tz, err := getUserTimeZone(id)
if err != nil {
    if errors.Is(err, ErrUserNotFound) {
        tz = time.UTC  // use default
    } else {
        return fmt.Errorf("get user %q: %w", id, err)
    }
}
```

### 预设失败策略
- Unsure where to log → log at the top-level handler; return errors from helpers
- Non-critical subsystem fails → log and degrade gracefully; don't propagate

---

## Error Flow: Indent the Error Path

### When
Writing any error-checking conditional.

### What
Handle errors first; keep the normal/success path at minimum indentation.

### How

```go
// Good: error exits early, normal code flows unindented
f, err := os.Open(name)
if err != nil {
    return err
}
d, err := f.Stat()
if err != nil {
    f.Close()
    return err
}
codeUsing(f, d)

// Bad: normal code buried in else
if err != nil {
    return err
} else {
    codeUsing(f)  // unnecessary indentation
}
```

For variables used across many lines, declare separately from the error check:

```go
// Good: x is visible and accessible
x, err := f()
if err != nil {
    return err
}
// many lines using x...
```

### 预设失败策略
- Deeply nested error chains → extract into smaller functions, each with a clear error contract
- `if x, err := f(); err != nil { } else { ... many lines... }` → pull declaration out

---

## Control Flow: Loops, Switch, Blank Identifier

### When
Writing loops, conditionals with multiple branches, or type assertions.

### What
Use Go's idiomatic control structures for clean, readable code.

### How

**if with initialization**: scope variables to the conditional block.

```go
if err := file.Chmod(0664); err != nil {
    return err
}
```

**Switch**: no automatic fall-through; use comma-separated cases.

```go
func shouldEscape(c byte) bool {
    switch c {
    case ' ', '?', '&', '=', '#', '+', '%':
        return true
    }
    return false
}
```

**Expression-less switch**: replaces `if-else-if` chains.

```go
switch {
case n < 0:
    return "negative"
case n == 0:
    return "zero"
default:
    return "positive"
}
```

**Type switch**: discover dynamic interface type.

```go
switch v := value.(type) {
case int:
    fmt.Printf("integer: %d\n", v)
case string:
    fmt.Printf("string: %q\n", v)
default:
    fmt.Printf("unexpected type %T\n", v)
}
```

**Blank identifier**: discard values intentionally, but never discard errors carelessly.

```go
// Good: only need presence check
_, present := cache[key]

// Bad: ignores error, will panic on nil dereference
fi, _ := os.Stat(path)
if fi.IsDir() { ... }
```

**Interface compliance check** (compile-time):

```go
var _ http.Handler = (*Handler)(nil)
```

### 预设失败策略
- `switch` getting too long → extract each case into a separate function
- Blank identifier on error → add a comment explaining why it's safe, or handle it
- Accidental variable shadowing in inner scope → check for `x, err :=` in a nested block where `x` is already declared
