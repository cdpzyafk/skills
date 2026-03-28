# Debugging Go Programs

Tools and techniques for finding and fixing bugs in Go code. Load this when diagnosing data races, profiling performance, inspecting goroutines, or stepping through code with a debugger.

---

## Data Race Detection

### When
Any time you suspect a data race, or as a routine CI check on concurrent code.

### What
The Go race detector instruments memory accesses at runtime and reports conflicting accesses from different goroutines.

### How

**Run tests with the race detector**:

```bash
go test -race ./...
go test -race -count=1 -timeout=60s ./...
```

**Run a binary with the race detector**:

```bash
go run -race main.go
go build -race -o myapp && ./myapp
```

**Interpret the output**:

```
WARNING: DATA RACE
Write at 0x00c000122070 by goroutine 7:
  main.(*Cache).Set(...)
      /app/cache.go:42

Previous read at 0x00c000122070 by goroutine 8:
  main.(*Cache).Get(...)
      /app/cache.go:31
```

Read the two goroutine stacks — one is the writer, one is the reader. The file:line tells you exactly where to add synchronization.

**Common fixes**:

```go
// Race: concurrent map access
// Fix: use sync.RWMutex
type Cache struct {
    mu   sync.RWMutex
    data map[string]string
}
func (c *Cache) Get(k string) string {
    c.mu.RLock()
    defer c.mu.RUnlock()
    return c.data[k]
}
func (c *Cache) Set(k, v string) {
    c.mu.Lock()
    defer c.mu.Unlock()
    c.data[k] = v
}
```

**Detect goroutine leaks in tests** — use `go.uber.org/goleak`:

```go
func TestMain(m *testing.M) {
    goleak.VerifyTestMain(m)
}

// Or per test:
func TestWorker(t *testing.T) {
    defer goleak.VerifyNone(t)
    // ...
}
```

### 预设失败策略
- Race not reproducible locally → run with `-count=100` to increase chances of triggering it
- Race in test setup/teardown → add `t.Parallel()` carefully; races often appear only with parallel tests
- Race detector too slow in CI → run only on a subset: `go test -race ./pkg/critical/...`

---

## pprof: CPU and Memory Profiling

### When
Code is slower or uses more memory than expected and you've confirmed this via benchmarks.

### What
`pprof` captures profiles of CPU usage and heap allocations and renders them as flamegraphs or call graphs.

### How

**Profile benchmarks** (easiest, no server needed):

```bash
# CPU profile
go test -bench=BenchmarkFoo -cpuprofile=cpu.out -count=5
go tool pprof -http=:8080 cpu.out

# Memory profile
go test -bench=BenchmarkFoo -memprofile=mem.out -count=5
go tool pprof -http=:8080 mem.out
```

**Profile a running HTTP server** — add the pprof handler:

```go
import _ "net/http/pprof" // registers /debug/pprof/* handlers

// In main(), if no existing HTTP server:
go func() {
    log.Println(http.ListenAndServe("localhost:6060", nil))
}()
```

Then capture and inspect:

```bash
# 30-second CPU profile
go tool pprof http://localhost:6060/debug/pprof/profile?seconds=30

# Heap snapshot
go tool pprof http://localhost:6060/debug/pprof/heap

# Goroutine stacks
curl http://localhost:6060/debug/pprof/goroutine?debug=2
```

**Reading the flamegraph**: width = time spent in that function (including callees). Look for the widest boxes at the top of the flame — those are the hottest paths.

**Key pprof commands inside the interactive CLI**:

```
top10          # top 10 functions by cumulative time
list FuncName  # annotated source for a function
web            # open flamegraph in browser
```

### 预设失败策略
- Profile shows `runtime.mallocgc` at the top → you have excessive allocations; look for slice growth in loops, use sync.Pool
- Profile shows syscall/network blocking → the bottleneck is I/O, not CPU; increase concurrency instead of optimizing code
- `net/http/pprof` import causes issues → move it to a dedicated internal debug server on a separate port

---

## go tool trace: Concurrency and Scheduler Tracing

### When
Goroutines seem to block unexpectedly, GC pauses are visible, or scheduler behavior is unclear.

### What
`trace` captures a timeline of goroutine scheduling, GC events, and network/syscall waits.

### How

**Capture a trace**:

```bash
# From a benchmark
go test -bench=BenchmarkFoo -trace=trace.out
go tool trace trace.out

# From a running server
curl http://localhost:6060/debug/pprof/trace?seconds=5 > trace.out
go tool trace trace.out
```

**What to look for in the UI**:
- **Goroutine analysis**: which goroutines are blocked, and why (channel, syscall, GC)
- **GC timeline**: frequency and duration of GC pauses
- **Scheduler latency**: time between goroutine becoming runnable and actually running

### 预设失败策略
- Trace file too large to open → capture for 1-2 seconds only
- GC pauses dominating → reduce allocation rate (see performance.md); tune `GOGC`
- All goroutines blocked on channel → suspect a deadlock or slow consumer; check channel buffer size

---

## Delve: Interactive Debugger

### When
A bug is not reproducible via tests, or you need to inspect program state step-by-step.

### What
`dlv` is the standard Go debugger — it understands goroutines, interfaces, and Go's runtime.

### How

**Install**:

```bash
go install github.com/go-delve/delve/cmd/dlv@latest
```

**Debug a program**:

```bash
dlv debug ./cmd/myapp          # build and launch under debugger
dlv debug ./cmd/myapp -- --port=8080  # with args
```

**Debug a test**:

```bash
dlv test ./pkg/orders -- -test.run TestProcessOrder
```

**Essential commands**:

```
break main.go:42        # set breakpoint at line 42
break (*OrderService).Execute  # break on method entry
continue (c)            # run until next breakpoint
next (n)                # step over
step (s)                # step into
stepout                 # step out of current function
print (p) varName       # print variable
locals                  # print all local variables
goroutines              # list all goroutines
goroutine N             # switch to goroutine N
stack                   # print call stack
quit (q)                # exit
```

**Attach to a running process**:

```bash
dlv attach <pid>
```

### 预设失败策略
- Optimized binary hard to debug → build with `go build -gcflags='-N -l'` to disable inlining and optimization
- Breakpoint never hit → verify the binary was built from the same source; check for build caching
- VS Code / GoLand integration → both use `dlv` underneath; configure launch.json to call `dlv dap`

---

## Goroutine Dumps

### When
Program is deadlocked, hanging, or goroutines are leaking in production.

### What
Dump the full stack of every goroutine to identify what each one is blocked on.

### How

**Trigger a goroutine dump via signal**:

```bash
# Send SIGQUIT to the process
kill -SIGQUIT <pid>

# Or set GOTRACEBACK before running
GOTRACEBACK=all ./myapp
```

**Dump from inside the program** (for tests or health endpoints):

```go
import "runtime"

func dumpGoroutines() []byte {
    buf := make([]byte, 1<<20)
    n := runtime.Stack(buf, true) // true = all goroutines
    return buf[:n]
}
```

**Reading the output** — each goroutine shows:
1. Goroutine ID and state (`running`, `chan receive`, `select`, `IO wait`, `sleep`)
2. Full call stack with file:line
3. Created-by line showing where the goroutine was spawned

```
goroutine 42 [chan receive]:          ← blocked on channel
main.(*Worker).Run(0xc000122040)
    /app/worker.go:55 +0x68
created by main.(*Pool).Start
    /app/pool.go:33 +0x4a
```

**GOTRACEBACK levels**:

| Value | Shows |
|-------|-------|
| `none` | No goroutine stacks |
| `single` | Only the failing goroutine (default) |
| `all` | All goroutines |
| `system` | All goroutines + runtime goroutines |
| `crash` | `system` + core dump |

### 预设失败策略
- Too many goroutines to read manually → grep for `[chan receive]` and `[select]` — those are usually the blocked ones
- Goroutines all blocked on same lock → the holder of that lock is the problem; find it by looking for the goroutine in `[running]` or `[syscall]` state
- Goroutine count growing over time → you have a leak; use `goleak` in tests to catch it early

---

## go vet and Static Analysis

### When
Before committing or as part of CI — catches bugs the compiler misses.

### What
`go vet` finds common mistakes: misuse of `Printf` format strings, unreachable code, suspicious constructs.

### How

```bash
go vet ./...
```

**Common findings**:

```go
// Printf format mismatch
fmt.Printf("%d", "not an int")       // vet: wrong type for verb

// Copying a sync type
var mu sync.Mutex
mu2 := mu                             // vet: assignment copies lock

// Loop variable capture (pre-Go 1.22)
for _, v := range items {
    go func() { use(v) }()           // vet: loop variable captured by closure
}
```

**Augment with staticcheck**:

```bash
go install honnef.co/go/tools/cmd/staticcheck@latest
staticcheck ./...
```

`staticcheck` catches additional issues: deprecated API usage, redundant nil checks, impossible type assertions.

### 预设失败策略
- `go vet` passes but bug still present → run `staticcheck` and `golangci-lint`
- False positive from vet → suppress with `//nolint:govet // reason` (never suppress without a comment)
- Loop variable capture warning (Go < 1.22) → add `v := v` inside the loop, or upgrade to Go 1.22+

---

## Quick Debugging Checklist

| Symptom | Tool | Command |
|---------|------|---------|
| Suspected data race | race detector | `go test -race ./...` |
| Goroutine leak | goleak | `defer goleak.VerifyNone(t)` |
| CPU bottleneck | pprof CPU | `go test -bench=. -cpuprofile=cpu.out` |
| Memory growth | pprof heap | `go test -bench=. -memprofile=mem.out` |
| GC pauses / scheduler | trace | `go test -bench=. -trace=trace.out` |
| Step-through debugging | delve | `dlv debug ./cmd/app` |
| Deadlock / hung process | goroutine dump | `kill -SIGQUIT <pid>` |
| Subtle code bugs | static analysis | `go vet ./...` + `staticcheck ./...` |
