# Foundation: Style, Naming, Packages, Documentation

Core Go style principles from Google and Uber style guides. Load this when questions arise about naming, code formatting, package organization, or documentation.

---

## Style Principles

### When
Writing any Go code — applies universally, every file, every function.

### What
Code should be clear, simple, concise, maintainable, and consistent — in that priority order.

### How

**Clarity first**: Code's purpose must be obvious to the reader, not just the author.

```go
// Good: clear purpose from name alone
func (c *Config) WriteTo(w io.Writer) (int64, error)

// Bad: repeats receiver, adds nothing
func (c *Config) WriteConfigTo(w io.Writer) (int64, error)
```

**Reduce nesting**: Handle errors and edge cases first; keep the happy path at minimal indentation.

```go
// Good: flat, error cases exit early
for _, v := range data {
    if v.F1 != 1 {
        log.Printf("Invalid v: %v", v)
        continue
    }
    v = process(v)
    if err := v.Call(); err != nil {
        return err
    }
    v.Send()
}
```

**Unnecessary else**: When an `if` body ends with `return`, omit the `else`.

```go
// Good
f, err := os.Open(name)
if err != nil {
    return err
}
codeUsing(f)

// Bad: else buries normal flow
if err != nil {
    return err
} else {
    codeUsing(f)
}
```

**Line length**: No hard limit, but avoid uncomfortably long lines. Break by semantics, not character count. When splitting function arguments, put each on its own line.

**gofmt**: Required, no exceptions. Run `gofmt -w .` or use `goimports` which also manages imports.

### 预设失败策略
- Clarity vs brevity conflict → always choose clarity
- Long lines → shorten names if they're the cause; otherwise wrap at semantic boundaries (before `.`, after `,`)
- Formatting debate → run `gofmt` and accept the output

---

## Naming

### When
Choosing any identifier name: packages, types, functions, methods, variables, constants.

### What
Names should not feel repetitive when used. Consider the full call context.

### How

**MixedCaps only**: `maxLength`, `MaxRetries`, `userID` — never `max_length`, `MAX_RETRIES`.

**Package names**: lowercase, no underscores, concise. Avoid `util`, `common`, `helper`, `model` — prefer `stringutil`, `httpauth`, `configloader`.

**Receiver names**: 1-2 letter abbreviation of the type, consistent across all methods.

```go
// Good: consistent short receiver
func (c *Client) Connect() error
func (c *Client) Send(msg []byte) error
func (c *Client) Close() error

// Bad: inconsistent and too long
func (client *Client) Connect() error
func (cl *Client) Send(msg []byte) error
func (this *Client) Close() error
```

**Initialisms**: keep consistent case throughout.

| English | Exported | Unexported |
|---------|----------|------------|
| URL | `URL` | `url` |
| ID | `ID` | `id` |
| HTTP | `HTTP` | `http` |

**Constants**: MixedCaps, never ALL_CAPS. Name by role, not value.

```go
const MaxRetries = 3        // Good: role
const MAX_RETRIES = 3       // Bad: snake_case
const Three = 3             // Bad: describes value, not role
```

**No Get prefix**: `Owner()` not `GetOwner()`. Use `Compute` or `Fetch` for expensive operations.

**Single-method interfaces**: `-er` suffix: `Reader`, `Writer`, `Formatter`.

**Avoid repetition**: context already provides meaning.

```go
// Bad: stutters
widget.NewWidget()
db.LoadFromDatabase()

// Good: concise
widget.New()
db.Load()
```

**Variable scope**: short names (`i`, `v`) for small scopes; longer names for larger scopes. Prefix unexported package-level vars with `_`: `const _defaultPort = 8080`.

**Function names**: MixedCaps throughout. Exception: test functions may use underscores to group related cases: `TestMyFunction_WhatIsBeingTested`.

**Avoid shadowing built-in identifiers** (`error`, `string`, `len`, `cap`, `new`, `make`, etc.). Shadowing is silent — the compiler won't warn, but `go vet` will catch some cases.

```go
// Bad: shadows the built-in error type
var error string

// Good
var errorMessage string

// Bad: struct fields named error/string create ambiguity
type Foo struct {
    error  error   // confusing: field vs type
    string string
}

// Good
type Foo struct {
    err error
    str string
}
```

### 预设失败策略
- Existing code uses non-standard naming → match local style within the file, add "Best Practice" comment
- Collision with common variable name → prefer renaming the more local/project-specific import
- Unclear whether to export → start unexported; export when there's a real consumer

---

## Packages and Imports

### When
Creating packages, organizing imports, using `init()`, or structuring code across files.

### What
Package organization should reflect cohesion, not just categorization.

### How

**Import organization** (normative):

```go
import (
    "fmt"          // stdlib first
    "os"

    "go.uber.org/atomic"           // external packages
    "golang.org/x/sync/errgroup"
)
```

Use `goimports` to manage this automatically.

**Avoid `import .`**: Makes it impossible to tell where names come from. Exception: circular test dependencies.

**Blank imports (`import _`)**: Only in `main` packages or tests.

**Import aliasing**: Required when the package name doesn't match the last element of the import path. Avoid otherwise — only alias to resolve a direct conflict.

```go
// Required: package name "client" but path ends in "client-go"
import (
    client "example.com/client-go"
    trace  "example.com/trace/v2"
)

// Good: only the conflicting import gets an alias
import (
    "runtime/trace"
    nettrace "golang.net/x/trace"
)

// Bad: unnecessary alias adds confusion
import (
    runtimetrace "runtime/trace" // no conflict; alias is noise
    nettrace     "golang.net/x/trace"
)
```

**Avoid `init()`**: Use explicit constructor functions that return errors instead.

```go
// Bad: init with I/O
func init() {
    raw, _ := os.ReadFile("config.yaml")
    yaml.Unmarshal(raw, &_config)
}

// Good: explicit, testable
func loadConfig() (Config, error) { ... }
```

**Exit only in `main()`**: Library functions return errors. Never call `log.Fatal` outside `main`.

**The `run()` pattern**:

```go
func main() {
    if err := run(); err != nil {
        log.Fatal(err)
    }
}

func run() error {
    // all logic here, can use defer
    return nil
}
```

### 预设失败策略
- Package growing too large → split when concepts are genuinely distinct, not just for size
- `init()` seems unavoidable → it must be deterministic, no I/O, no environment dependencies
- Import cycle detected → restructure packages; do not use `import .` as a workaround

---

## Documentation

### When
Writing or reviewing any exported identifier, package, or non-obvious unexported function.

### What
Documentation should explain what the code does and why — what the reader cannot deduce from the code itself.

### How

**Doc comments** (normative): Every exported name needs one. Begin with the name.

```go
// A Request represents a request to run a command.
type Request struct { ... }

// Encode writes the JSON encoding of req to w.
func Encode(w io.Writer, req *Request) { ... }
```

**Package comments**: One per package, immediately above the `package` clause.

```go
// Package math provides basic constants and mathematical functions.
package math
```

**Signal boosting**: Add comments to highlight non-obvious patterns.

```go
if err := doSomething(); err == nil { // if NO error
    // ...
}
```

**Document cleanup**: Always document explicit cleanup requirements.

```go
// Call Stop to release the Ticker's associated resources when done.
func NewTicker(d Duration) *Ticker
```

**Don't over-document**: Don't restate what the code already says. Document exceptions, not implied behavior.

```go
// Bad: Restates the obvious
// Run executes the worker's run loop. The method will process work
// until the context is cancelled.

// Good: Just the essential
// Run executes the worker's run loop.
func (Worker) Run(ctx context.Context) error
```

**Preview docs**: `pkgsite` renders godoc locally for validation.

### 预设失败策略
- Unsure if a comment is needed → document if the behavior would surprise a reader
- Comment feels repetitive → delete it; the code is the documentation
- Named result parameters → only use them when types alone don't clarify (e.g., multiple same-type returns)

---

## Structured Logging with slog

### When
Adding logging to any production Go service (Go 1.21+). Prefer `log/slog` for all new code.

### What
`log/slog` is the standard structured logger in Go 1.21+. It replaces ad-hoc `log.Printf` and reduces the need for third-party loggers in new projects.

### How

**Basic usage — structured key-value pairs**:

```go
// Good: machine-parseable, searchable
slog.Info("order processed", "orderID", order.ID, "amount", order.Amount)
slog.Error("payment failed", "orderID", order.ID, "err", err)

// Bad: string formatting loses structure
log.Printf("order processed: orderID=%s amount=%v", order.ID, order.Amount)
```

**Configure JSON output in `main()`**:

```go
func main() {
    slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
        Level: slog.LevelInfo,
    })))
}
```

**Inject logger as a dependency** — never use `slog.Default()` in library code:

```go
type OrderService struct {
    log *slog.Logger
}

func NewOrderService(log *slog.Logger) *OrderService {
    return &OrderService{log: log.With("component", "order-service")}
}

func (s *OrderService) Process(ctx context.Context, order Order) error {
    s.log.InfoContext(ctx, "processing order", "orderID", order.ID)
    // ...
}
```

**Use context-aware variants** (`InfoContext`, `ErrorContext`) — they allow middleware to attach trace IDs:

```go
// Good: middleware can inject trace ID into ctx
slog.InfoContext(ctx, "request received", "path", r.URL.Path)
```

**Stable fields with `With()`** — set once at construction, not on every call:

```go
// Good: component and service appear on every log line automatically
log := slog.Default().With("service", "payment", "env", os.Getenv("ENV"))
```

**Log levels**:
| Level | Use for |
|-------|---------|
| `Debug` | Fine-grained detail, dev only |
| `Info` | Normal operational events |
| `Warn` | Unexpected but handled |
| `Error` | Failures requiring attention |

### 预设失败策略
- Already using `zap` → keep it for existing projects; use `slog` for new ones
- Where to create the root logger → only in `main()`; inject everywhere else
- Key name for errors → use `"err"` by convention: `slog.Error("msg", "err", err)`
- Too many fields per call → use `.With()` at construction for stable fields; add dynamic fields per call

---

## Code Organization

### When
Structuring declarations within a file, ordering functions, deciding where types and helpers live.

### Group Similar Declarations

Group related `const`, `var`, `type`, and `import` declarations with parentheses:

```go
// Good: grouped
const (
    a = 1
    b = 2
)

var (
    a = 1
    b = 2
)

// Bad: separate declarations
const a = 1
const b = 2
```

Only group **related** items — don't mix unrelated constants in one block:

```go
// Bad: mixes operation constants with an env var
const (
    Add Operation = iota + 1
    Subtract
    EnvVar = "MY_ENV" // unrelated!
)

// Good: separate blocks
const (
    Add Operation = iota + 1
    Subtract
)
const EnvVar = "MY_ENV"
```

This applies inside functions too — group local variable declarations together when they appear adjacent:

```go
// Good
var (
    caller  = c.name
    format  = "json"
    timeout = 5 * time.Second
)
```

### Function Grouping and Ordering

- Sort functions in rough **call order** (callers before callees helps readers follow the narrative)
- Group functions by **receiver** — all methods on a type live together
- Exported functions appear **first** in a file, after `struct`/`const`/`var` definitions
- `newXYZ()` appears right after the type definition, before other methods
- Plain utility functions (no receiver) go at the end of the file

```go
// Good ordering
type something struct{ ... }

func newSomething() *something { ... }

func (s *something) Cost() int { return calcCost(s.weights) }
func (s *something) Stop()     { ... }

func calcCost(n []int) int { ... } // utility at end
```

### 预设失败策略
- Unrelated items grouped together → split into separate blocks with a blank line between them
- Utility functions mixed in with methods → move to end of file
- Unsure about function order → put the entry point or most-called function first

---

## Variable Declarations

### When
Declaring variables at the top level or inside functions — choosing between `var`, `:=`, and explicit types.

### Top-level Variables

Use `var` without a type when the expression type already matches what you want. Only add the type when the expression type differs from the desired type (e.g., assigning to an interface):

```go
// Good: type is inferred
var _s = F()

// Bad: redundant type annotation
var _s string = F()

// Necessary exception: F() returns *myError, but we want the error interface
var _e error = F()
```

Unexported top-level `var`s and `const`s should be prefixed with `_` to signal they are package-level globals and prevent accidental shadowing:

```go
const (
    _defaultPort = 8080
    _defaultUser = "user"
)
```

Exception: unexported error values use `err` prefix without underscore: `var errNotFound = errors.New("not found")`.

### Local Variable Declarations

Use `:=` when assigning an explicit value. Use `var` when the zero value is meaningful (especially for slices and structs where nil/zero is the right default):

```go
// Good: setting a value
s := "foo"

// Good: zero value is intentional — nil slice preferred over empty slice
var filtered []int

// Bad: creates a non-nil empty slice (behaves differently in JSON)
filtered := []int{}
```

### Reduce Scope of Variables

Use `if`-initialization to scope variables to the block where they're needed:

```go
// Good: err scoped to the if block
if err := os.WriteFile(name, data, 0644); err != nil {
    return err
}

// Bad: err leaks into enclosing scope unnecessarily
err := os.WriteFile(name, data, 0644)
if err != nil {
    return err
}
```

Don't reduce scope if it conflicts with readability — when the result is used after the block, or when nesting would increase:

```go
// Good: data is needed after the if block — don't scope it inside
data, err := os.ReadFile(name)
if err != nil {
    return err
}
if err := cfg.Decode(data); err != nil { // err re-scoped, data available
    return err
}
```

### 预设失败策略
- `:=` vs `var` unclear → if you're providing an initial value, use `:=`; if zero value is the point, use `var`
- Scope reduction causing deeper nesting → prefer the longer form; readability wins
- Top-level var accumulating type noise → check whether the type is obvious from the expression; if so, drop it

---

## Readability Patterns

### When
Writing function calls with multiple parameters, string literals, struct literals, or Printf-family functions.

### Avoid Naked Parameters

Boolean or magic-value parameters without clear names hurt readability. Add `/* name */` comments when meaning isn't obvious from context:

```go
// Bad: what do true, true mean?
printInfo("foo", true, true)

// Good: meaning is clear
printInfo("foo", true /* isLocal */, true /* done */)
```

Better yet, use custom types instead of bare booleans — this prevents mixing up argument order and allows more than two states later:

```go
type Region int

const (
    UnknownRegion Region = iota
    Local
    Remote
)

type Status int

const (
    StatusReady Status = iota + 1
    StatusDone
)

func printInfo(name string, region Region, status Status)
```

### Raw String Literals

Use backtick strings to avoid escape sequences — they're easier to read and maintain:

```go
// Bad: escaping is noise
wantError := "unknown name:\"test\""

// Good: unescaped and clear
wantError := `unknown name:"test"`
```

### Initializing Structs

**Always specify field names** when initializing structs (enforced by `go vet`):

```go
// Bad: positional — breaks if fields reorder
k := User{"John", "Doe", true}

// Good: named, explicit
k := User{
    FirstName: "John",
    LastName:  "Doe",
    Admin:     true,
}
```

Exception: field names may be omitted in test tables when there are 3 or fewer fields.

**Omit zero-value fields** unless they provide meaningful context:

```go
// Good: zero values are implied
user := User{
    FirstName: "John",
    LastName:  "Doe",
}

// Bad: noise from explicit zeros
user := User{
    FirstName:  "John",
    LastName:   "Doe",
    MiddleName: "",    // unnecessary
    Admin:      false, // unnecessary
}
```

**Use `var` for fully zero-value structs** (distinguishes "zero" from "initialized"):

```go
var user User   // Good: clearly zero-valued
user := User{}  // OK but redundant — `var` is cleaner
```

**Use `&T{}` not `new(T)`** for pointer initialization — consistent with struct literal syntax:

```go
// Good: consistent style
sptr := &T{Name: "bar"}

// Bad: inconsistent — requires separate field assignment
sptr := new(T)
sptr.Name = "bar"
```

### Printf Format Strings

Format strings outside `Printf` calls should be `const` — this allows `go vet` to perform static analysis:

```go
// Good: go vet can validate the format
const msg = "unexpected values %v, %v\n"
fmt.Printf(msg, 1, 2)

// Bad: go vet can't check a variable format string
msg := "unexpected values %v, %v\n"
fmt.Printf(msg, 1, 2)
```

Custom `Printf`-style functions must end with `f` for `go vet` to check them:

```go
func Wrapf(format string, args ...any) error  // Good: go vet checks format
func Wrap(format string, args ...any) error   // Bad: go vet doesn't know about this
```

Run: `go vet -printfuncs=wrapf,statusf` to register custom `Printf`-style functions.

### 预设失败策略
- Bool parameters confusing → add `/* isLocal */` comment; if multiple callers are confused, create a custom type
- Struct literal with positional args → always add field names; `go vet` will flag this
- Printf custom function not being checked by vet → ensure it ends with `f` and register with `-printfuncs`
