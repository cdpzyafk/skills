# Concurrency and Context

Go concurrency patterns from Google and Uber style guides. Load this when spawning goroutines, working with channels, using mutexes, or propagating context.Context.

---

## Goroutine Lifetimes

### When
Any time you write `go func()` or `go someFunc()`.

### What
Every goroutine must have a predictable exit — a way to stop it and a way to wait for it to finish.

### How

```go
// Good: goroutine lifetime is clear and controlled
func (w *Worker) Run(ctx context.Context) error {
    var wg sync.WaitGroup
    for item := range w.q {
        wg.Add(1)
        go func() {
            defer wg.Done()
            process(ctx, item) // exits when context cancelled
        }()
    }
    wg.Wait()
    return nil
}

// Bad: no exit strategy, no way to wait
func (w *Worker) Run() {
    for item := range w.q {
        go process(item) // when does this finish?
    }
}
```

**Stop/done channel pattern** for background loops:

```go
var (
    stop = make(chan struct{})
    done = make(chan struct{})
)
go func() {
    defer close(done)
    ticker := time.NewTicker(delay)
    defer ticker.Stop()
    for {
        select {
        case <-ticker.C:
            flush()
        case <-stop:
            return
        }
    }
}()

// To shut down:
close(stop)
<-done
```

**Waiting with WaitGroup**:

```go
var wg sync.WaitGroup
for i := 0; i < N; i++ {
    wg.Add(1)
    go func() {
        defer wg.Done()
        // work...
    }()
}
wg.Wait()
```

**Never spawn goroutines in `init()`**: expose an object with a `Shutdown()` or `Close()` method instead.

### 预设失败策略
- "I just need a quick background task" → still needs a shutdown mechanism; use the stop/done pattern
- Goroutine leaking in tests → use `go.uber.org/goleak` to detect
- Context cancelled but goroutine still running → check `<-ctx.Done()` in the select loop

---

## Synchronous Functions First

### When
Designing a new function that processes work.

### What
Prefer synchronous functions — it's much easier to add concurrency at the caller than to remove it from a function.

### How

```go
// Good: synchronous — caller adds concurrency if needed
func ProcessItems(items []Item) ([]Result, error) {
    var results []Result
    for _, item := range items {
        result, err := processItem(item)
        if err != nil {
            return nil, err
        }
        results = append(results, result)
    }
    return results, nil
}

// Caller can wrap in goroutine if needed:
go func() {
    results, err := ProcessItems(items)
    // handle...
}()
```

### 预设失败策略
- Performance too slow as synchronous → CPU-bound: `workerPool(N=runtime.GOMAXPROCS(0))`; IO-bound: bounded goroutines with semaphore `make(chan struct{}, 10)`. Don't guess — pick one, benchmark, adjust N.
- Function "needs" to be async → document exactly what it blocks on; always provide a `Stop()` or `Close()` method

---

## Mutexes

### When
Protecting shared mutable state accessed by multiple goroutines.

### What
Use zero-value `sync.Mutex` as a named field — never embed, never take a pointer.

### How

```go
// Good: named field, zero-value valid
type SMap struct {
    mu   sync.Mutex
    data map[string]string
}

func (m *SMap) Get(k string) string {
    m.mu.Lock()
    defer m.mu.Unlock()
    return m.data[k]
}

// Bad: embedded mutex leaks Lock/Unlock into API
type SMap struct {
    sync.Mutex // now SMap.Lock() and SMap.Unlock() are exported methods
    data map[string]string
}

// Bad: unnecessary pointer
mu := new(sync.Mutex)
```

### 预设失败策略
- Struct being copied elsewhere → copying a struct with a mutex is almost always a bug; use a pointer
- RWMutex vs Mutex → default `sync.Mutex`; switch to `sync.RWMutex` only when reads vastly outnumber writes (10:1+) AND lock contention appears in benchmarks

---

## Channels

### When
Orchestrating goroutines, passing ownership of data, or signaling events.

### What
Channels should have a deliberate direction and size. Default to unbuffered or size-1.

### How

**Always specify direction** where possible:

```go
// Good: direction makes ownership clear
func produce(out chan<- int) { /* send-only */ }
func consume(in <-chan int)  { /* receive-only */ }
func transform(in <-chan int, out chan<- int) { /* both */ }

// Bad: bidirectional allows accidental misuse
func sum(values chan int) (out int) {
    for v := range values {
        out += v
    }
    close(values) // Bug! Compiles but shouldn't happen
}
```

**Channel size**: unbuffered (0) or size-1 by default. Any other size needs justification.

```go
// Good: deliberate sizing
c := make(chan int)    // unbuffered
c := make(chan int, 1) // size 1

// Questionable: who decided 64? what if it fills up?
c := make(chan int, 64)
```

### 预设失败策略
- Channel full and writer is blocking → the consumer is the bottleneck; don't increase buffer size (it just delays the problem) — add more consumers or slow down the producer
- Sending on closed channel panic → never close from the sender side if multiple senders exist; use a `sync.Once` or a dedicated "done" signaling pattern

---

## Atomic Operations

### When
Reading or writing a single value from multiple goroutines without a mutex.

### What
Use `go.uber.org/atomic` for type-safety — raw `sync/atomic` makes it easy to accidentally forget the atomic operation on a read.

### How

```go
// Good: type-safe, can't accidentally read non-atomically
type foo struct {
    running atomic.Bool
}

func (f *foo) start() {
    if f.running.Swap(true) {
        return // already running
    }
}

func (f *foo) isRunning() bool {
    return f.running.Load()
}

// Bad: easy to forget atomic.LoadInt32 on reads
type foo struct {
    running int32 // atomic
}

func (f *foo) isRunning() bool {
    return f.running == 1 // race condition!
}
```

### 预设失败策略
- Unclear whether mutex or atomic → use mutex for anything beyond a single bool/int flag; atomics compose poorly

---

## Context Usage

### When
Writing any function that does I/O, network calls, database queries, or long-running computation.

### What
Pass `context.Context` as the first parameter to propagate cancellation, deadlines, and request-scoped values.

### How

```go
// Good: context is first parameter
func ProcessRequest(ctx context.Context, req *Request) (*Response, error) {
    // ...
}

// Bad: context stored in struct (lifetime unclear)
type Worker struct {
    ctx context.Context
}
```

**Never create custom context types**:

```go
// Bad: custom type breaks composability
type MyContext interface {
    context.Context
    GetUserID() string
}

// Good: extract from context value
func Process(ctx context.Context) error {
    userID := UserIDFromContext(ctx)
    // ...
}
```

**Application data priority**: function params > receiver fields > globals > context values.

Context values are appropriate for:
- Request IDs, trace IDs
- Auth/authorization info flowing with requests
- Deadlines and cancellation

**Deriving contexts**:

```go
ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
defer cancel() // always defer cancel to release resources

ctx, cancel := context.WithCancel(ctx)
defer cancel()
```

**Checking cancellation in long loops**:

```go
func LongOperation(ctx context.Context) error {
    for {
        select {
        case <-ctx.Done():
            return ctx.Err()
        default:
            // do work
        }
    }
}
```

**Use `context.Background()` only** in `main()` or top-level initialization — never in business logic.

### 预设失败策略
- Function doesn't need context "right now" → accept it anyway; changing a signature later breaks all callers
- Context value vs parameter → if the data varies per request, context is fine; if it's fixed configuration, use a constructor parameter
- `context.TODO()` → use only as a temporary placeholder when refactoring; remove before merging

---

## Graceful Shutdown

### When
Writing any long-running service: HTTP servers, background workers, message consumers.

### What
On receiving SIGINT/SIGTERM: stop accepting new work, drain in-flight requests, close dependencies in order, then exit.

### How

**Standard HTTP server shutdown** (the canonical pattern):

```go
func run(ctx context.Context) error {
    srv := &http.Server{
        Addr:    ":8080",
        Handler: buildRouter(),
    }

    // Start server; ErrServerClosed is expected on shutdown — not an error
    go func() {
        if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
            slog.Error("server error", "err", err)
        }
    }()

    <-ctx.Done() // wait for SIGINT/SIGTERM

    // Give in-flight requests up to 30s to complete
    shutdownCtx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
    defer cancel()
    return srv.Shutdown(shutdownCtx)
}

func main() {
    // signal.NotifyContext (Go 1.16+): context cancelled on SIGINT or SIGTERM
    ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
    defer stop()

    if err := run(ctx); err != nil {
        log.Fatal(err)
    }
}
```

**Multi-component coordinated shutdown** — use `errgroup`:

```go
func run(ctx context.Context) error {
    g, ctx := errgroup.WithContext(ctx)
    g.Go(func() error { return runHTTPServer(ctx) })
    g.Go(func() error { return runWorker(ctx) })
    g.Go(func() error { return runMetrics(ctx) })
    return g.Wait() // first error cancels all others via ctx
}
```

**Worker / consumer shutdown** — always select on `ctx.Done()`:

```go
func (w *Worker) Run(ctx context.Context) error {
    for {
        select {
        case <-ctx.Done():
            return ctx.Err()
        case msg := <-w.queue:
            if err := w.process(ctx, msg); err != nil {
                slog.ErrorContext(ctx, "process failed", "err", err)
            }
        }
    }
}
```

**Shutdown order**: stop accepting → drain in-flight → close dependencies (DB, message queue, cache).

### 预设失败策略
- `http.ErrServerClosed` treated as error → always check and ignore it; it's normal
- Shutdown timeout → default 30s; tune to `2 × p99 request latency`
- Multiple servers need to shut down together → use `errgroup.WithContext`
- Background goroutine not stopping on shutdown → verify it selects on `<-ctx.Done()`

---

## Documenting Thread Safety

### When
Writing a type or function whose concurrency characteristics aren't obvious from its name.

### What
Document when read operations mutate state, when the API provides synchronization, or when callers must coordinate.

### How

```go
// When read-only operation actually mutates (e.g., LRU cache)
// Lookup returns the data for key from the cache.
//
// This operation is not safe for concurrent use.
func (*Cache) Lookup(key string) (data []byte, ok bool)

// When the API is explicitly thread-safe
// It is safe for simultaneous use by multiple goroutines.
func NewFortuneTellerClient(cc *rpc.ClientConn) *FortuneTellerClient
```

### 预设失败策略
- Unsure if safe → document "not safe for concurrent use" conservatively; you can relax it later
- Type has mixed safe/unsafe methods → document each method individually
