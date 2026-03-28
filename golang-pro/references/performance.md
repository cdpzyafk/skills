# Data Structures and Performance

Go data structures and performance patterns from Effective Go and the Uber Go Style Guide. Load this when choosing data structures, working with slices/maps, or optimizing hot paths.

---

## new vs make

### When
Allocating memory for any type.

### What
Use `new` for zeroed allocation of any type; use `make` for slices, maps, and channels only.

### How

```go
// new: returns *T with zero value
p := new(SyncedBuffer)  // *SyncedBuffer, zero value

// make: initializes slices, maps, channels
s := make([]int, 10, 100)        // len=10, cap=100
m := make(map[string]int)        // empty, ready to use
c := make(chan int)               // unbuffered channel

// Common mistake:
var p *[]int = new([]int)    // *p == nil, rarely useful
var v []int = make([]int, 10) // v is a usable slice of 10 ints
```

**Zero-value design**: design structs so they're useful at zero value without further initialization (`bytes.Buffer`, `sync.Mutex`).

### 预设失败策略
- `new` returning something not useful → switch to `make` or a constructor function
- Need to allocate and initialize → use a composite literal: `&Config{Name: "foo"}`

---

## Slices

### When
Working with sequences of elements.

### What
Slices are the primary collection type in Go — use them by default over arrays.

### How

**Declare empty slices**: prefer `var t []string` (nil) over `t := []string{}` (non-nil, zero-length). They're functionally equivalent for `len`, `cap`, and `append`.

**Exception for JSON**: nil slice → `null`; empty slice (`[]string{}`) → `[]`. Use non-nil when you need a JSON array.

**Always assign append result** — the underlying array may change:

```go
x = append(x, 4, 5, 6)
x = append(x, y...)  // append a slice
```

**Pre-allocate with capacity** on hot paths:

```go
// Good: zero reallocations until capacity is reached
data := make([]int, 0, size)
for k := 0; k < size; k++ {
    data = append(data, k)
}

// Bad: repeated reallocations (~12x slower)
data := make([]int, 0)
```

**Avoid aliasing bugs** — copying a struct whose methods are on `*T` is always wrong:

```go
// Bad: buf2's internal slice aliases buf1's array
buf2 := buf1  // bytes.Buffer has methods on *Buffer

// Good: always use pointers for such types
buf2 := &bytes.Buffer{}
buf2.Write(buf1.Bytes())
```

### 预设失败策略
- Slice length unknown at declaration → use `make([]T, 0, estimatedSize)` with a reasonable estimate; over-estimating is fine
- JSON `null` vs `[]` discrepancy → initialize with `[]T{}` explicitly when JSON output matters
- Interface boundary returning nil slice → return `[]T{}` — callers should never need to nil-check a returned collection

---

## Maps

### When
Associating keys with values. Keys must support `==`.

### What
Maps are reference types — nil maps panic on write but are safe to read.

### How

**Always initialize before writing**:

```go
m := make(map[string]int)  // or: m := map[string]int{}
m["key"] = 1               // safe

var m map[string]int
m["key"] = 1               // panic: assignment to nil map
```

**Presence check with comma-ok**:

```go
value, ok := m[key]
if !ok {
    return fmt.Errorf("key %q not found", key)
}
```

**Pre-size when length is known**:

```go
// Good: hint reduces rehashing
m := make(map[string]os.DirEntry, len(files))
for _, f := range files {
    m[f.Name()] = f
}
```

**Implementing a set**:

```go
visited := map[string]bool{"alice": true, "bob": true}
if visited[name] { ... } // false if not in map
```

**`make` vs map literals**: use `make` for empty maps or maps populated programmatically; use a literal for maps with a fixed set of elements known at init time:

```go
// Good: make for programmatic population (can add size hint later)
m := make(map[string]os.DirEntry, len(files))
for _, f := range files {
    m[f.Name()] = f
}

// Good: literal for fixed elements
m := map[T1]T2{
    k1: v1,
    k2: v2,
    k3: v3,
}

// Bad: make + manual assignment when literal would be cleaner
m := make(map[T1]T2, 3)
m[k1] = v1
m[k2] = v2
m[k3] = v3
```

The distinction matters for readability: `make` signals "this is going to grow", a literal signals "this is the complete set".

### 预设失败策略
- Concurrent map read/write → use `sync.RWMutex` or `sync.Map` (the latter for write-once, read-many patterns)
- Map key is a struct → ensure all fields support `==`; slices and maps cannot be keys

---

## Performance: Hot Path Optimizations

### When
Code has been profiled and a specific path is the bottleneck. **Never optimize without first benchmarking.**

### What
Apply targeted optimizations to the measured hot path only.

### How

**Prefer `strconv` over `fmt` for primitive conversions**:

```go
// Good: ~2x faster, 1 alloc/op
s := strconv.Itoa(n)

// Slower: ~2 allocs/op
s := fmt.Sprint(n)
```

**Convert strings to bytes once, outside loops**:

```go
// Good: ~7x faster
data := []byte("Hello world")
for i := 0; i < N; i++ {
    w.Write(data)
}

// Bad: allocates new slice every iteration
for i := 0; i < N; i++ {
    w.Write([]byte("Hello world"))
}
```

**Pass values, not pointers, for small fixed-size types**:

```go
// Good: no indirection, no heap allocation
func process(s string) { fmt.Println(s) }

// Bad: pointer for "saving bytes" is counterproductive for strings
func process(s *string) { fmt.Println(*s) }
```

Common types that should be passed by value: `string`, `io.Reader` (interface), small structs with no mutable fields.

Exceptions: large structs where copying is expensive, or small structs expected to grow.

**`sync.Pool` for frequently allocated objects**:

```go
var bufPool = sync.Pool{
    New: func() any { return new(bytes.Buffer) },
}

func process() {
    buf := bufPool.Get().(*bytes.Buffer)
    buf.Reset()
    defer bufPool.Put(buf)
    // use buf...
}
```

### 预设失败策略
- No benchmark yet → stop. Write `go test -bench=BenchmarkFoo -benchmem` first. Optimizing without measurement is guesswork that introduces bugs.
- `sync.Pool` not helping → it's only useful for objects with GC pressure; measure before adding complexity
- String builder vs concatenation → use `strings.Builder` in loops; `+` is fine for 2-3 concatenations

---

## Constants and iota

### When
Defining enumerated or grouped constant values.

### What
Use `iota` for auto-incremented constants; combine with methods for self-describing output.

### How

```go
type ByteSize float64

const (
    _           = iota // ignore first value
    KB ByteSize = 1 << (10 * iota)
    MB
    GB
    TB
)

func (b ByteSize) String() string {
    switch {
    case b >= GB:
        return fmt.Sprintf("%.2fGB", b/GB)
    case b >= MB:
        return fmt.Sprintf("%.2fMB", b/MB)
    case b >= KB:
        return fmt.Sprintf("%.2fKB", b/KB)
    }
    return fmt.Sprintf("%.2fB", b)
}
```

### 预设失败策略
- `String()` calls itself recursively → convert to base type first: `fmt.Sprintf("%.2f", float64(b)/float64(GB))`
- iota values used in serialized formats → define explicit values instead; iota is fragile when values are persisted
