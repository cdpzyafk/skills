# Go System Architecture

Go-specific guidance for structuring services and codebases at the system level. Load this when designing a new service, organizing packages across layers, choosing between communication patterns, or evaluating macro-level trade-offs.

**Table of contents:**
1. [The Core Constraint](#1-the-core-constraint)
2. [Project Layout](#2-project-layout)
3. [Package Organization](#3-package-organization)
4. [Layered Service Architecture](#4-layered-service-architecture)
5. [Dependency Injection](#5-dependency-injection)
6. [Service Communication](#6-service-communication)
7. [Configuration](#7-configuration)
8. [Observability Wiring](#8-observability-wiring)
9. [Architecture Anti-Patterns](#9-architecture-anti-patterns)

---

## 1. The Core Constraint

### When
Before making any architectural decision.

### What
Architecture decisions should answer a real constraint, not demonstrate design sophistication. Over-engineering is the most common Go architectural mistake.

### How

Ask four questions before adding structural complexity:

1. What constraint does this solve? (latency / throughput / team isolation / deployment independence / data consistency)
2. What is the simplest structure that satisfies that constraint?
3. Is the complexity being added essential (comes from the problem) or accidental (comes from the solution)?
4. If I knew only today's requirements, would I make the same choice?

**Common patterns and their true constraints:**

| Pattern | Use when this constraint is REAL | Skip when |
|---------|----------------------------------|-----------|
| Microservices | Teams need independent deployment; services need asymmetric scaling | A monolith handles it fine |
| Event-driven | Producer/consumer must be temporally decoupled; async is required | Synchronous calls are sufficient |
| CQRS | Read model and write model are fundamentally different | Read/write are symmetric |
| Repository pattern | You need to swap storage backends or mock for tests | You have one storage backend and will never change it |
| Service layer | Business logic must be reused by multiple transport layers | Only one entry point (HTTP only) |

### 预设失败策略
- "We might need to scale this later" → design for today's real load; add complexity when it's justified
- Pattern X is popular → ask what constraint it solves; if your system doesn't have that constraint, skip it

---

## 2. Project Layout

### When
Starting a new Go service or module.

### What
Go doesn't mandate a project layout. The standard community layout (adapted from golang-standards/project-layout) works well for services — but don't cargo-cult it for CLIs or libraries.

### How

**Service layout (the common case):**

```
my-service/
├── cmd/
│   └── my-service/
│       └── main.go          # Only wiring: flags, config, DI, server start
├── internal/                # Cannot be imported by external packages
│   ├── handler/             # HTTP/gRPC transport layer
│   ├── service/             # Business logic
│   ├── repository/          # Data access
│   └── domain/              # Core types, errors, interfaces
├── pkg/                     # Exported packages safe for external use
│   └── client/              # SDK for callers of this service
├── config/                  # Config file templates, embedded defaults
├── migrations/              # Database schema migrations
├── docs/                    # Design docs (YYYYMMDD-feature.md)
└── go.mod
```

**Key rules:**
- `main.go` does wiring only — create dependencies, inject them, start the server, handle signals
- `internal/` enforces package boundaries that the compiler itself enforces
- `pkg/` is for code you intentionally want external callers to import
- Don't create `pkg/` just because you see it in other repos — only if you genuinely have exportable packages

**Library layout (simpler):**

```
mylib/
├── foo.go          # Exported API
├── foo_test.go
├── internal/       # Implementation details
└── go.mod
```

**CLI layout:**

```
mytool/
├── cmd/
│   ├── root.go     # cobra root command
│   ├── serve.go
│   └── migrate.go
├── internal/
└── main.go
```

### 预设失败策略
- "Should I use /pkg?" → only if code is genuinely intended for external callers; if unsure, put it in `internal/`
- "How deep should the directory tree go?" → depth should reflect genuine modularity, not folder aesthetics; 2-3 levels is usually enough

---

## 3. Package Organization

### When
Deciding how to split code across packages within a module.

### What
Packages should be cohesive — everything in a package should work together toward a single purpose. Packages split by type (all `structs` here, all `interfaces` there) produce circular dependencies and tight coupling.

### How

**Package cohesion rules:**

```
// Bad: organized by kind (produces coupling and circular deps)
models/    user.go, order.go, product.go
services/  user_service.go, order_service.go
handlers/  user_handler.go, order_handler.go

// Good: organized by feature (each package is self-contained)
user/      handler.go, service.go, repository.go, model.go
order/     handler.go, service.go, repository.go, model.go
```

**Dependency direction must be acyclic:**

```
cmd/ → internal/handler → internal/service → internal/repository
                                           → internal/domain
```

`domain` is the base — it imports nothing internal. Every layer above it imports downward, never upward.

**Package naming:**
- Lowercase, no underscores: `orderservice` not `order_service`
- Name the package, not the directory: if directory is `auth/`, package is `auth`, not `authpkg`
- Avoid `util`, `common`, `helpers` — these become catch-all junk drawers
- If you can't name a package without using "and" — it needs to be split

**When to split a package:**
- Circular dependency appears → the two packages have wrong boundaries
- Package exceeds ~3000 LOC with genuinely distinct responsibilities
- A subset of the package is used independently → that subset earns its own package

**When NOT to split:**
- Just to reduce file size — Go handles large files fine
- "It feels cleaner" without a functional reason

### 预设失败策略
- Circular import error → the packages are at the wrong abstraction level; extract a shared `domain` package that both can import
- Package name collision with stdlib → rename yours, never alias the stdlib

---

## 4. Layered Service Architecture

### When
Building any backend service with non-trivial business logic.

### What
Separate transport (HTTP/gRPC) from business logic from data access. Each layer has a clear responsibility and a defined interface boundary.

### How

**The three-layer pattern:**

```go
// domain/order.go — core types and interface contracts
type Order struct {
    ID     string
    Amount decimal.Decimal
    Status OrderStatus
}

type OrderRepository interface {  // defined here (consumer), not in repository/
    Create(ctx context.Context, order *Order) error
    FindByID(ctx context.Context, id string) (*Order, error)
}

type OrderService interface {     // defined here (consumer), not in service/
    PlaceOrder(ctx context.Context, req PlaceOrderRequest) (*Order, error)
}
```

```go
// service/order.go — business logic, no HTTP or SQL knowledge
type orderService struct {
    repo   domain.OrderRepository
    events domain.EventPublisher
    log    *slog.Logger
}

func NewOrderService(repo domain.OrderRepository, events domain.EventPublisher, log *slog.Logger) domain.OrderService {
    return &orderService{repo: repo, events: events, log: log.With("component", "order-service")}
}

func (s *orderService) PlaceOrder(ctx context.Context, req PlaceOrderRequest) (*Order, error) {
    // pure business logic: validation, calculation, state transitions
}
```

```go
// handler/order.go — HTTP concerns only: parse, validate transport, delegate, encode
type OrderHandler struct {
    service domain.OrderService
}

func (h *OrderHandler) PlaceOrder(w http.ResponseWriter, r *http.Request) {
    // decode request → call service → encode response
    // NO business logic here
}
```

```go
// repository/postgres_order.go — SQL concerns only
type postgresOrderRepo struct {
    db *sql.DB
}

func (r *postgresOrderRepo) Create(ctx context.Context, order *domain.Order) error {
    // SQL only, no business logic
}
```

**Layer rules:**
- Handler knows nothing about SQL; repository knows nothing about HTTP
- All dependencies flow inward toward `domain`
- `domain` has zero dependencies on internal packages — it's the core
- Services receive their dependencies via constructor injection (never from globals)

### 预设失败策略
- Business logic creeping into handlers → handler sees a decision tree (if/else based on domain state) → move it to service
- Repository doing validation → validation belongs in service; repo just persists
- "I only have one storage backend, do I need the interface?" → if you want to unit-test the service without a real DB, yes; otherwise, a thin struct is fine

---

## 5. Dependency Injection

### When
Wiring up the application components in `main` or in tests.

### What
Manual constructor injection in `main.go` is idiomatic Go for most services. Wire (google/wire) adds value only when the dependency graph is large and changes frequently.

### How

**Manual DI in main.go (the standard approach):**

```go
func run(ctx context.Context, cfg *config.Config) error {
    // Infrastructure
    db, err := postgres.Open(cfg.DatabaseURL)
    if err != nil {
        return fmt.Errorf("open database: %w", err)
    }
    defer db.Close()

    log := slog.New(slog.NewJSONHandler(os.Stdout, nil))

    // Data layer
    orderRepo := repository.NewPostgresOrderRepo(db)

    // Service layer
    eventPub := events.NewKafkaPublisher(cfg.KafkaBrokers, log)
    orderSvc := service.NewOrderService(orderRepo, eventPub, log)

    // Transport layer
    orderHandler := handler.NewOrderHandler(orderSvc)

    // Router
    mux := http.NewServeMux()
    mux.Handle("/orders", orderHandler)

    // Start server with graceful shutdown
    srv := &http.Server{Addr: cfg.Addr, Handler: mux}
    // ... signal handling ...
    return nil
}
```

**When to consider Wire:**
- 20+ components with complex interdependencies
- Dependency graph changes frequently (team adding services often)
- You want compile-time validation of the wiring

**Never use init() for wiring** — it runs before `main()`, can't return errors, can't accept arguments, and is invisible to the reader.

### 预设失败策略
- `init()` is used for database connection → move it into a constructor function with proper error return
- Global variables used as implicit dependencies → inject explicitly via constructor; globals make tests unpredictable

---

## 6. Service Communication

### When
Deciding how services or components talk to each other.

### What
Choose the simplest communication mechanism that satisfies the actual decoupling and performance constraints. Don't add message queues or gRPC because they're impressive.

### How

**Decision table:**

| Use | When |
|-----|------|
| Direct function call | Same process; no network boundary |
| HTTP/REST | Cross-service; human-readable payloads; wide client compatibility |
| gRPC | Cross-service; high-throughput; strong typing via protobuf; streaming |
| Message queue (Kafka/NATS) | Producer and consumer must be temporally decoupled; fan-out; replay needed |
| In-process channel | Goroutine coordination within the same service |

**HTTP patterns:**

```go
// Client with timeout and base URL — never use http.DefaultClient in production
type OrderClient struct {
    base   string
    client *http.Client
}

func NewOrderClient(base string) *OrderClient {
    return &OrderClient{
        base: base,
        client: &http.Client{Timeout: 10 * time.Second},
    }
}

func (c *OrderClient) GetOrder(ctx context.Context, id string) (*Order, error) {
    req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.base+"/orders/"+id, nil)
    if err != nil {
        return nil, fmt.Errorf("build request: %w", err)
    }
    resp, err := c.client.Do(req)
    // ... handle response ...
}
```

**gRPC server setup:**

```go
func runGRPC(ctx context.Context, svc domain.OrderService) error {
    lis, err := net.Listen("tcp", ":9090")
    if err != nil {
        return fmt.Errorf("listen: %w", err)
    }
    s := grpc.NewServer(
        grpc.ChainUnaryInterceptor(
            grpcrecovery.UnaryServerInterceptor(),
            otelgrpc.UnaryServerInterceptor(),
        ),
    )
    pb.RegisterOrderServiceServer(s, handler.NewGRPCOrderHandler(svc))
    go func() {
        <-ctx.Done()
        s.GracefulStop()
    }()
    return s.Serve(lis)
}
```

**Retry and circuit breaker** (add when transient failures are expected):

```go
// Use github.com/sony/gobreaker or failsafe-go
cb := gobreaker.NewCircuitBreaker(gobreaker.Settings{
    Name:        "order-service",
    MaxRequests: 3,
    Timeout:     30 * time.Second,
    ReadyToTrip: func(counts gobreaker.Counts) bool {
        return counts.ConsecutiveFailures > 5
    },
})
```

### 预设失败策略
- "Should I use gRPC or REST?" → REST unless you need streaming, very high throughput, or strong schema contracts across teams
- "Should I use Kafka?" → only if consumers need to work asynchronously or you need fan-out; otherwise HTTP/gRPC is simpler

---

## 7. Configuration

### When
Loading runtime configuration for any Go service.

### What
12-factor: config comes from the environment. Use a typed config struct loaded at startup; never access `os.Getenv` directly in business logic.

### How

**Config struct pattern:**

```go
// config/config.go
type Config struct {
    Addr        string        `env:"ADDR,default=:8080"`
    DatabaseURL string        `env:"DATABASE_URL,required"`
    LogLevel    slog.Level    `env:"LOG_LEVEL,default=INFO"`
    ShutdownTimeout time.Duration `env:"SHUTDOWN_TIMEOUT,default=30s"`
}

// Load parses environment variables into Config.
func Load() (*Config, error) {
    var cfg Config
    if err := envconfig.Process("", &cfg); err != nil {  // github.com/kelseyhightower/envconfig
        return nil, fmt.Errorf("load config: %w", err)
    }
    return &cfg, nil
}
```

**In main.go:**

```go
cfg, err := config.Load()
if err != nil {
    log.Fatal(err)
}
```

**Config is loaded once in main**, then injected. Never call `os.Getenv` in service or repository code — it makes the behavior unpredictable and untestable.

**Feature flags:** use a boolean field in `Config`. External feature flag systems (LaunchDarkly, etc.) are justified only for production A/B testing; don't add the dependency speculatively.

### 预设失败策略
- `os.Getenv` inside business logic → move to `Config` struct, load at startup
- Config struct with 30+ fields → group into nested structs (`cfg.Database`, `cfg.Kafka`, `cfg.HTTP`)
- YAML/JSON config files → fine for Kubernetes deployments, but still parse into a typed struct; never read config files directly from service code

---

## 8. Observability Wiring

### When
Adding logging, metrics, and tracing to a service.

### What
Observability is a system-level concern — set it up in `main`, inject it into components, don't let components reach out to global singletons.

### How

**The three signals and where they belong:**

```go
// main.go — set up all observability infrastructure once
func run(ctx context.Context, cfg *Config) error {
    // Logging: inject structured logger
    log := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
        Level: cfg.LogLevel,
    })).With("service", "order-service", "version", version)

    // Metrics: initialize Prometheus registry (or OTEL)
    reg := prometheus.NewRegistry()
    reg.MustRegister(collectors.NewGoCollector(), collectors.NewProcessCollector(...))

    // Tracing: initialize OTEL tracer provider
    tp, err := initTracer(cfg.JaegerEndpoint)
    if err != nil {
        return fmt.Errorf("init tracer: %w", err)
    }
    defer tp.Shutdown(ctx)

    // Inject into components
    orderRepo := repository.NewPostgresOrderRepo(db, log, reg)
    orderSvc  := service.NewOrderService(orderRepo, log, reg)
    // ...
}
```

**In service methods — use context-aware logging and tracing:**

```go
func (s *orderService) PlaceOrder(ctx context.Context, req PlaceOrderRequest) (*Order, error) {
    ctx, span := tracer.Start(ctx, "order-service.PlaceOrder")
    defer span.End()

    s.log.InfoContext(ctx, "placing order", "amount", req.Amount)
    // ...
}
```

**Structured logging field conventions:**
- `"err"` for errors
- `"duration_ms"` for latency
- `"order_id"`, `"user_id"` for domain IDs
- `"component"` set once in constructor via `log.With("component", "...")`

**Health endpoints** (expose for every service):

```go
mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
    // liveness: am I running?
    w.WriteHeader(http.StatusOK)
})
mux.HandleFunc("/readyz", func(w http.ResponseWriter, r *http.Request) {
    // readiness: can I serve traffic? (check DB, dependencies)
    if err := db.PingContext(r.Context()); err != nil {
        http.Error(w, "db not ready", http.StatusServiceUnavailable)
        return
    }
    w.WriteHeader(http.StatusOK)
})
mux.Handle("/metrics", promhttp.HandlerFor(reg, promhttp.HandlerOpts{}))
```

### 预设失败策略
- Using `slog.Default()` inside service/repo → inject the logger; `slog.Default()` is for `main`-level code only
- `logrus.WithField(...)` or `zap` global → for new services, use `log/slog`; for existing codebases, wrap the existing logger but inject it
- No `/readyz` endpoint → add it; Kubernetes readiness probes require it

---

## 9. Architecture Anti-Patterns

### Over-engineering Signals

| You see this... | The real problem |
|----------------|-----------------|
| More packages than types | Organized by kind, not cohesion — produces circular deps |
| Interface for every struct | Abstraction before need — YAGNI |
| 5+ layers between HTTP and SQL | Indirection without a constraint justifying it |
| `utils/`, `helpers/`, `common/` packages | No one decided where things belong |
| `init()` wiring dependencies | Invisible startup order; can't return errors |
| `http.DefaultClient` in production | Shared client; no timeouts; will cause cascading failures |
| `os.Getenv` in service code | Config is an implicit global; untestable |
| Goroutines in `init()` | No shutdown path; leaks on signal |

### Under-engineering Signals

| You see this... | The real problem |
|----------------|-----------------|
| Business logic in HTTP handlers | Can't reuse; can't test without HTTP |
| SQL in service methods | Can't test business logic without DB |
| All code in `main.go` | Works until it doesn't; impossible to test |
| `context.Background()` in service methods | Cancellation and tracing are broken |
| No graceful shutdown | `SIGTERM` kills in-flight requests |
| No structured logging | Logs unsearchable in production |

### The right level of complexity

A CRUD service with a DB: `cmd/ → handler → service → repository → postgres`. That's it. Don't add event sourcing, CQRS, or a service mesh until a real constraint forces you.

A service at 100k QPS with fan-out to 10 downstream services: add circuit breakers, retries, bounded concurrency, metrics on every callsite. The complexity earns its keep.

**The test**: can you explain the architecture in 2 sentences? If not, it might be too complex for the problem.
