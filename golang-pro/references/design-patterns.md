# Design Patterns: Interfaces, Functional Options, Defensive Coding

Go design patterns from Google, Uber, and Effective Go. Load this when designing APIs, implementing interfaces, choosing between patterns, or writing defensive production-quality code.

---

## Interface Design

### When
Designing a type that needs to be substitutable, testable, or extensible.

### What
Define small, focused interfaces at the consumer — not at the implementor. Return concrete types from constructors.

### How

**Accept interfaces, return structs** (the core rule):

```go
// Good: constructor returns concrete type, hides implementation
func NewHash() hash.Hash32 {
    return &myHash{} // unexported type
}

// Good: function accepts interface — any type with Write() works
func WriteJSON(w io.Writer, v any) error { ... }
```

**Interface location**: define in the package that *uses* it, not the package that implements it. This avoids circular dependencies and premature abstraction.

**Don't pre-define interfaces**: only define an interface when you have 2+ concrete implementations or need to mock for testing.

**Single-method interface naming**: `-er` suffix: `Reader`, `Writer`, `Stringer`, `Subscriber`.

**Interface embedding** to compose behaviors:

```go
type ReadWriter interface {
    Reader
    Writer
}
```

**Receiver type** — use pointer when:
- Method mutates receiver
- Receiver contains `sync.Mutex` or similar (never copy it)
- Struct is large
- Any other method already uses pointer receiver (be consistent)

Use value when: small, immutable type with no pointer fields.

**Consistency rule**: never mix pointer and value receivers on the same type.

**Compile-time interface check**:

```go
// Fails at compile time if *Handler doesn't implement http.Handler
var _ http.Handler = (*Handler)(nil)
```

**Type assertions** — always use comma-ok to avoid panics:

```go
str, ok := value.(string)
if ok {
    // use str
}
```

### 预设失败策略
- Only one implementation exists → don't define the interface yet; add it when the second implementation appears
- Interface definition growing large → split into smaller interfaces (Interface Segregation)
- Value vs pointer receiver unclear → use pointer; you can always relax it, but changing from value to pointer breaks callers
- Returning interface from constructor "for flexibility" → usually wrong; return the concrete type unless implementation is truly private

---

## Receivers and Interfaces: Addressability Rules

### When
Assigning types to interface variables, storing types in maps/slices, or mixing value and pointer receivers.

### What
The Go spec's addressability rules determine which receiver types satisfy which interfaces. Getting this wrong causes subtle compile errors.

### How

**Value receivers** are callable on both values and pointers:

```go
func (s S) Read() string { return s.data }

sVals := map[int]S{1: {"A"}}
sVals[1].Read() // OK: value receiver works on map values

sPtrs := map[int]*S{1: {"A"}}
sPtrs[1].Read() // OK: value receiver works on pointers too
```

**Pointer receivers** require a pointer or addressable value. Map values are NOT addressable:

```go
func (s *S) Write(str string) { s.data = str }

sVals := map[int]S{1: {"A"}}
// sVals[1].Write("test") // Compile error: map values are not addressable

sPtrs := map[int]*S{1: {"A"}}
sPtrs[1].Write("test") // OK: map of pointers works fine
```

**Interface satisfaction**: a pointer type `*T` satisfies an interface requiring value receiver methods, but `T` (value) does NOT satisfy an interface requiring pointer receiver methods:

```go
type F interface { f() }

type S1 struct{}
func (s S1) f() {}   // value receiver

type S2 struct{}
func (s *S2) f() {}  // pointer receiver

var i F
i = S1{}   // OK: value receiver — both value and pointer satisfy F
i = &S1{}  // OK
i = &S2{}  // OK: pointer satisfies F
// i = S2{} // Compile error: S2 has pointer receiver, S2 value doesn't satisfy F
```

**Rule**: if any method on a type uses a pointer receiver, always use `*T` in interface variable assignments.

### 预设失败策略
- "does not implement interface" error → check if all methods have consistent receiver kinds; likely need `*T` in the interface assignment
- Map value won't accept pointer receiver call → store `*T` in the map instead of `T`
- Mixed value and pointer receivers → make all receivers consistent; Go allows it but it's confusing

---

## Embedding in Structs: When It's Appropriate

### When
Deciding whether to embed a type vs storing it as a named field.

### What
Embedding promotes the embedded type's methods to the outer type's API. This is only appropriate when ALL those methods genuinely belong there.

### How

**Embedding IS appropriate** when the embedded type's exported methods add meaningful functionality to the outer type, and you're intentionally extending its API:

```go
// Good: io.WriteCloser methods (Write, Close) belong on countingWriteCloser's API
type countingWriteCloser struct {
    io.WriteCloser // Write and Close are intentionally part of this type's contract

    count int
}

// Override Write to count bytes, delegate the rest
func (w *countingWriteCloser) Write(bs []byte) (int, error) {
    w.count += len(bs)
    return w.WriteCloser.Write(bs)
}
```

**Embedding is NOT appropriate** when:
- It's purely cosmetic (saves writing delegate methods)
- The embedded type exposes methods you don't want in the outer API
- Embedding would affect the zero value usefulness
- The embedded type is a pointer (breaks zero value)

```go
// Bad: sync.Mutex methods become exported API of A
type A struct {
    sync.Mutex // A.Lock() and A.Unlock() are now public — callers can control internals
}

// Good: mutex is an implementation detail
type A struct {
    mu sync.Mutex
}

// Bad: embedded pointer breaks zero value
type Book struct {
    io.ReadWriter // var b Book; b.Read(...) → panic: nil pointer
}

// Good: bytes.Buffer has a useful zero value
type Book struct {
    bytes.Buffer // var b Book; b.Read(...) → OK
}
```

**Position rule**: embedded types go at the TOP of the field list, separated from regular fields by a blank line:

```go
// Good: embedding at top, blank line separator
type Client struct {
    http.Client

    version int
    timeout time.Duration
}

// Bad: embedded type buried among fields
type Client struct {
    version int
    http.Client
    timeout time.Duration
}
```

**Litmus test**: "Would ALL exported methods and fields of the embedded type be added directly to the outer type?" If the answer is "some" or "no" — use a named field instead.

### 预设失败策略
- Embedding "because it's convenient" → write the delegate methods; the cost is worth the API clarity
- Embedded pointer type → switch to value embedding or named field
- Mutex embedded → always a named field `mu sync.Mutex`
- Embedding adds breaking-change risk → every future version of the outer type must keep the embedded type

---

## Functional Options

### When
A constructor or function has 3+ optional parameters, or the API needs to evolve without breaking callers.

### What
Allow callers to specify only the options they care about, with sensible defaults for the rest.

### How

**Core pattern** (interface approach, preferred over closures):

```go
// 1. Unexported options struct
type options struct {
    cache  bool
    logger *zap.Logger
}

// 2. Exported Option interface with unexported method
type Option interface {
    apply(*options)
}

// 3. Option types + constructors
type cacheOption bool
func (c cacheOption) apply(opts *options) { opts.cache = bool(c) }
func WithCache(c bool) Option            { return cacheOption(c) }

type loggerOption struct{ Log *zap.Logger }
func (l loggerOption) apply(opts *options) { opts.logger = l.Log }
func WithLogger(log *zap.Logger) Option    { return loggerOption{Log: log} }

// 4. Constructor applies options over defaults
func Open(addr string, opts ...Option) (*Connection, error) {
    o := options{
        cache:  true,             // sensible default
        logger: zap.NewNop(),
    }
    for _, opt := range opts {
        opt.apply(&o)
    }
    return &Connection{}, nil
}
```

**Caller experience**:

```go
// Only specify what differs from defaults
db.Open(addr)
db.Open(addr, db.WithLogger(log))
db.Open(addr, db.WithCache(false), db.WithLogger(log))
```

**Why interface over closure?**
- Options are comparable in tests
- Options can implement `fmt.Stringer` for debugging
- Option types are visible in documentation

**When to use config struct instead**: fewer than 3 options, or all options are usually specified together.

### 预设失败策略
- Options struct becoming unwieldy → break into logical groups; required params go in the constructor signature, optional ones stay as `Option`s
- Want to validate options → validate in the constructor after applying all options, not in individual `apply()` methods
- Option ordering matters → document it; or redesign so order doesn't matter

---

## Defensive Coding

### When
Writing production-quality code that handles edge cases, API boundaries, and resource management.

### What
Protect invariants at boundaries; use Go's features to make safe behavior the default.

### How

**Copy slices and maps at API boundaries**:

```go
// Receiving: copy before storing, or caller can mutate your internals
func (d *Driver) SetTrips(trips []Trip) {
    d.trips = make([]Trip, len(trips))
    copy(d.trips, trips)
}

// Returning: return a copy, not a reference to internal state
func (s *Stats) Snapshot() map[string]int {
    s.mu.Lock()
    defer s.mu.Unlock()
    result := make(map[string]int, len(s.counters))
    for k, v := range s.counters {
        result[k] = v
    }
    return result
}
```

**Use `defer` for cleanup**:

```go
// Good: defer immediately after acquiring resource
f, err := os.Open(filename)
if err != nil {
    return err
}
defer f.Close()

// Good: defer for locks — no missed unlocks
p.Lock()
defer p.Unlock()
if p.count < 10 {
    return p.count // unlock happens automatically
}
```

**Enums start at 1** (not 0) to distinguish uninitialized from valid:

```go
// Good: zero value = uninitialized
const (
    Add Operation = iota + 1
    Subtract
    Multiply
)

// Exception: when zero is the sensible default
```

**Always use `time.Time` and `time.Duration`**, never raw `int` for time:

```go
// Good
func isActive(now, start, stop time.Time) bool { ... }
func poll(delay time.Duration) { time.Sleep(delay) }

// Bad: seconds? milliseconds? unknowable
func poll(delay int) { time.Sleep(time.Duration(delay) * time.Millisecond) }
```

**Dependency injection over mutable globals**:

```go
// Good: inject time.Now for testability
type signer struct {
    now func() time.Time
}

func newSigner() *signer {
    return &signer{now: time.Now}
}
```

**Avoid embedding types in public structs**: embedding leaks implementation details and makes type evolution impossible.

```go
// Bad: embedding AbstractList makes ConcreteList's API fragile
type ConcreteList struct {
    *AbstractList
}

// Good: explicit delegation
type ConcreteList struct {
    list *AbstractList
}
func (l *ConcreteList) Add(e Entity)    { l.list.Add(e) }
func (l *ConcreteList) Remove(e Entity) { l.list.Remove(e) }
```

**Always use struct field tags** for marshaled structs:

```go
// Good: serialization contract is explicit
type Stock struct {
    Price int    `json:"price"`
    Name  string `json:"name"`
}
```

**Use `crypto/rand` for keys**, never `math/rand`:

```go
import "crypto/rand"

func Key() string {
    return rand.Text()
}
```

**Panic and recover**:
- `panic` only for truly unrecoverable situations (programming errors, impossible states)
- Library functions should never panic — return errors instead
- Use `recover` in deferred functions at goroutine/server boundaries to convert panics to errors
- Never expose panics across package boundaries

```go
func safelyDo(work *Work) (err error) {
    defer func() {
        if r := recover(); r != nil {
            err = fmt.Errorf("work panicked: %v", r)
        }
    }()
    return do(work)
}
```

### 预设失败策略
- Slice returned to caller gets modified unexpectedly → always copy at the boundary
- Test requires manipulating time → inject `func() time.Time` instead of using `time.Now()` directly
- Panic escaping a package → add a recover in the exported entry points; never let panics cross package boundaries
- Embedding is "convenient" → convenience now means fragility later; use explicit delegation
