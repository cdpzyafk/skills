# Exchange Client Design Patterns

Best practices for building Go exchange clients — HTTP and WebSocket, public and private APIs — distilled from the gocryptotrader codebase. Load this when designing or implementing exchange integrations, trading clients, or any system with REST + WebSocket market data feeds.

## Table of Contents

1. [Exchange Interface & Base Composition](#1-exchange-interface--base-composition)
2. [HTTP Request Infrastructure](#2-http-request-infrastructure)
3. [Authentication & HMAC Signing](#3-authentication--hmac-signing)
4. [Error Handling](#4-error-handling)
5. [Retry & Backoff Logic](#5-retry--backoff-logic)
6. [WebSocket Architecture](#6-websocket-architecture)
7. [Subscription Management](#7-subscription-management)
8. [Keepalive & Reconnection](#8-keepalive--reconnection)
9. [Orderbook Real-time Management](#9-orderbook-real-time-management)
10. [Financial Data Types](#10-financial-data-types)

---

## 1. Exchange Interface & Base Composition

### When
Designing an exchange client that must support multiple exchanges with a uniform API surface.

### Pattern: Interface + Embedded Base

Define a large interface (`IBotExchange`) that all exchange implementations must satisfy. Share infrastructure through an embedded `Base` struct rather than inheritance.

```go
// The universal interface — all exchanges implement this
type IBotExchange interface {
    SetDefaults()
    Setup(exch *config.Exchange) error
    GetName() string
    GetBase() *Base

    // Market data
    FetchTradablePairs(ctx context.Context, a asset.Item) (currency.Pairs, error)
    UpdateOrderbook(ctx context.Context, p currency.Pair, a asset.Item) (*orderbook.Book, error)
    GetHistoricCandles(ctx context.Context, pair currency.Pair, a asset.Item, interval kline.Interval, start, end time.Time) (*kline.Item, error)

    // Account (authenticated)
    GetCredentials(ctx context.Context) (*accounts.Credentials, error)
    ValidateAPICredentials(ctx context.Context, a asset.Item) error
    // ... 100+ more methods
}

// Concrete exchange embeds Base, adds exchange-specific fields
type Exchange struct {
    exchange.Base
    obm *orderbookManager // exchange-specific
}
```

### Initialization: Two-Phase Setup

Separate static defaults from config-driven initialization:

```go
// Phase 1: SetDefaults() — called first, sets everything that doesn't depend on user config
func (e *Exchange) SetDefaults() {
    e.Name = "Binance"
    e.API.CredentialsValidator.RequiresKey = true
    e.API.CredentialsValidator.RequiresSecret = true

    // Configure pair formats per asset type
    e.CurrencyPairs.Store(asset.Spot, currency.PairStore{
        RequestFormat: &currency.PairFormat{Uppercase: true},   // "BTCUSDT"
        ConfigFormat:  &currency.PairFormat{Uppercase: true, Delimiter: "-"}, // "BTC-USD"
    })

    // Declare supported features
    e.Features.Supports.RESTCapabilities.TickerBatching = true
    e.Features.Supports.Websocket = true

    // Create rate-limited HTTP requester
    e.Requester, _ = request.New(e.Name, request.NewRateLimit(time.Minute, 1200))

    // Create WebSocket manager
    e.Websocket = websocket.NewManager()
}

// Phase 2: Setup() — called second, loads from user config
func (e *Exchange) Setup(exch *config.Exchange) error {
    if err := e.SetupDefaults(exch); err != nil { // base method
        return err
    }
    return e.Websocket.Setup(&websocket.ManagerSetup{
        ExchangeConfig: exch,
        DefaultURL:     wsURL,
        Connector:      e.WsConnect,
        Subscriber:     e.Subscribe,
        GenerateSubscriptions: e.generateSubscriptions,
    })
}
```

### 预设失败策略
- Don't mix static and dynamic setup → split strictly: `SetDefaults()` for constants, `Setup()` for user config
- Multiple asset types → each gets its own pair format, rate limits, and WS channels
- Credentials in tests → use `DeployCredentialsToContext(ctx, creds)` to inject without mutating global state

---

## 2. HTTP Request Infrastructure

### When
Building the HTTP layer for exchange communication — especially when authentication requires fresh timestamps on every attempt.

### Pattern: Generate Closure for Retry-Safe Requests

The central insight: **signatures expire**. HMAC-signed requests include timestamps within a `recvWindow` (usually 5s). On retry, you must re-sign with a fresh timestamp. Solve this with a `Generate` closure that creates a fresh request on each attempt:

```go
type Generate func() (*Item, error)

func (r *Requester) SendPayload(
    ctx context.Context,
    ep EndpointLimit,      // identifies the rate limit bucket
    newRequest Generate,   // called fresh on every retry attempt
    requestType AuthType,  // UnauthenticatedRequest or AuthenticatedRequest
) error {
    for attempt := 1; ; attempt++ {
        if err := r.InitiateRateLimit(ctx, ep); err != nil {
            return err
        }
        item, err := newRequest() // regenerate request with current timestamp
        if err != nil {
            return err
        }
        resp, err := r.execute(ctx, item)
        shouldRetry, retryErr := r.evaluateRetry(ctx, resp, err, attempt)
        if !shouldRetry {
            return retryErr
        }
    }
}
```

**Why Generate instead of passing `*Item` directly**: if you pre-build the item with `timestamp=T`, any retry after recvWindow expires will get rejected by the exchange. The closure captures the credentials/params by reference and rebuilds with `time.Now()` on each call.

### Pattern: Weighted Per-Endpoint Rate Limiting

Exchanges assign different "weights" to different endpoints (e.g., Binance: depth@5000 = weight 250, order placement = weight 1):

```go
type EndpointLimit uint16
const (
    SpotPublic    EndpointLimit = iota
    SpotOrders
    SpotOrderbook5000 // weight 250
)

type RateLimitDefinitions map[any]*RateLimiterWithWeight

type RateLimiterWithWeight struct {
    limiter *rate.Limiter  // golang.org/x/time/rate
    weight  int
}

// Reserve `weight` tokens, not just 1
func (r *RateLimiterWithWeight) RateLimit(ctx context.Context) error {
    reservation := r.limiter.ReserveN(time.Now(), r.weight)
    delay := reservation.Delay()
    // respect context deadline before sleeping
    if dl, ok := ctx.Deadline(); ok && dl.Before(time.Now().Add(delay)) {
        reservation.Cancel()
        return context.DeadlineExceeded
    }
    select {
    case <-time.After(delay):
        return nil
    case <-ctx.Done():
        reservation.Cancel()
        return ctx.Err()
    }
}
```

### Pattern: Context-Based Controls

Pass per-request behavior through context rather than method signatures:

```go
// Override credentials for a single call (useful in tests or multi-account)
ctx = accounts.DeployCredentialsToContext(ctx, &accounts.Credentials{
    Key:    "test-key",
    Secret: "test-secret",
})

// Disable retry for this call (e.g., in tests where you want immediate failure)
ctx = request.WithRetryNotAllowed(ctx)

// Disable rate limit delay (for integration tests)
ctx = request.WithDelayNotAllowed(ctx)

// Enable verbose logging for a single request without changing global flag
ctx = request.WithVerbose(ctx)
```

### 预设失败策略
- Stale signature errors (code -1021 Binance) → ensure `newRequest` closure captures `time.Now()` at call time, not construction time
- Rate limit unclear → define an `EndpointLimit` iota for every distinct rate bucket; don't share one limiter across endpoints with different weights
- Cross-service HTTP client sharing → wrap `*http.Client` in a tracker that prevents reuse; cross-service sharing causes timeout contamination

---

## 3. Authentication & HMAC Signing

### When
Implementing authenticated (private) REST endpoints.

### Pattern: Credentials from Context

Never hard-code or store credentials globally where requests are made. Retrieve them from context at request-generation time, enabling context-based override:

```go
func (e *Exchange) sendAuthRequest(ctx context.Context, method, path string, params url.Values, result any) error {
    return e.SendPayload(ctx, SpotOrders, func() (*request.Item, error) {
        creds, err := e.GetCredentials(ctx) // checks context first, then defaults
        if err != nil {
            return nil, err
        }

        // Timestamp inside closure — fresh on every retry attempt
        ts := strconv.FormatInt(time.Now().UnixMilli(), 10)
        params.Set("timestamp", ts)
        params.Set("recvWindow", "5000") // acceptable clock skew window

        sig, _ := crypto.GetHMAC(crypto.HashSHA256,
            []byte(params.Encode()),
            []byte(creds.Secret))

        return &request.Item{
            Method: method,
            Path:   e.getEndpoint() + path + "?" + params.Encode() + "&signature=" + hex.EncodeToString(sig),
            Headers: map[string]string{
                "X-MBX-APIKEY": creds.Key,
            },
            Result: result,
        }, nil
    }, request.AuthenticatedRequest)
}
```

### Signing Variants Across Exchanges

| Exchange | Timestamp format | Signature payload | Encoding | Extra header |
|----------|-----------------|-------------------|----------|--------------|
| Binance  | `UnixMilli()` ms | `queryString` | hex | `X-MBX-APIKEY` |
| OKX      | `RFC3339` UTC | `timestamp + METHOD + path + body` | base64 | `OK-ACCESS-PASSPHRASE` (ClientID) |
| Bybit    | `UnixMilli()` ms | `ts + key + recvWindow + (query or body)` | hex | `X-BAPI-API-KEY`, `X-BAPI-RECV-WINDOW` |

**OKX example** (HMAC over method+path+body, base64 encoded, requires passphrase):
```go
utcTime := time.Now().UTC().Format(time.RFC3339)
hmac, _ := crypto.GetHMAC(crypto.HashSHA256,
    []byte(utcTime+method+"/api/v5/"+path+string(jsonBody)),
    []byte(creds.Secret))

headers["OK-ACCESS-KEY"] = creds.Key
headers["OK-ACCESS-SIGN"] = base64.StdEncoding.EncodeToString(hmac)
headers["OK-ACCESS-TIMESTAMP"] = utcTime
headers["OK-ACCESS-PASSPHRASE"] = creds.ClientID // third credential field
```

**GET vs POST handling** (Bybit):
```go
switch method {
case http.MethodGet:
    // Sign query params as string
    toSign = ts + creds.Key + recvWindow + params.Encode()
    headers["Content-Type"] = "application/x-www-form-urlencoded"
case http.MethodPost:
    // Sign JSON body
    body, _ = json.Marshal(arg)
    toSign = ts + creds.Key + recvWindow + string(body)
    headers["Content-Type"] = "application/json"
}
headers["X-BAPI-SIGN"] = hexHMAC(toSign, creds.Secret)
```

### Credentials Struct

```go
type Credentials struct {
    Key                 string // API key
    Secret              string // Signing secret
    ClientID            string // OKX passphrase; Coinbase "profile ID"
    PEMKey              string // Certificate-based auth
    SubAccount          string // Sub-account routing
    OneTimePassword     string // 2FA OTP
    SecretBase64Decoded bool   // Flag: secret needs base64 decode before use
}
```

### 预设失败策略
- "Invalid signature" after rotation → credentials were cached at construction time; call `GetCredentials(ctx)` inside the Generate closure, not outside
- OKX "passphrase wrong" error → `ClientID` carries the passphrase, not a client identifier; verify the field is set
- Base64-encoded secrets → set `SecretBase64Decoded = false` and let the credential system decode before passing to HMAC

---

## 4. Error Handling

### When
Parsing HTTP responses from exchange APIs, which use exchange-specific error envelopes.

### Pattern: Three-layer error parsing

```go
// Layer 1: HTTP transport/status errors
if resp.StatusCode < 200 || resp.StatusCode > 204 {
    return fmt.Errorf("%s: HTTP %d: %s", exchangeName, resp.StatusCode, body)
}

// Layer 2: Exchange envelope unwrap
var envelope struct {
    Code int64  `json:"code"` // 0 = success on OKX, 200 on Binance
    Msg  string `json:"msg"`
    Data json.RawMessage `json:"data"`
}
json.Unmarshal(body, &envelope)

// Layer 3: Map to semantic errors
if envelope.Code != 0 {
    if mapped, ok := ErrorCodes[strconv.FormatInt(envelope.Code, 10)]; ok {
        return mapped  // typed error callers can match with errors.Is
    }
    return fmt.Errorf("exchange error %d: %s", envelope.Code, envelope.Msg)
}
```

### Pattern: Error Code Tables

Map exchange-specific numeric codes to package-level `var` errors:

```go
var (
    ErrInvalidSign   = errors.New("invalid sign")
    ErrRequestsLimit = errors.New("requests too frequent")
)

var ErrorCodes = map[string]error{
    "60007": ErrInvalidSign,
    "60014": ErrRequestsLimit,
    // ...50+ entries
}
```

This lets callers use `errors.Is(err, ErrRequestsLimit)` without string matching.

### Pattern: Auth error wrapping

When an authenticated request fails, tag the error so callers can distinguish "wrong credentials" from "network error":

```go
if requestType == AuthenticatedRequest && err != nil {
    err = fmt.Errorf("%w: %w", ErrAuthRequestFailed, err)
}
```

### 预设失败策略
- Exchange returns HTTP 200 with error inside body → always check the envelope after status check; HTTP 200 doesn't mean success
- Multiple errors in batch responses (e.g., Bybit `RetExtInfo.List`) → iterate the per-item error list, don't just check the top-level code
- Unknown error codes → return a formatted string with the raw code and message; don't silently swallow them

---

## 5. Retry & Backoff Logic

### When
Implementing automatic retry for transient failures.

### Pattern: Pluggable retry policy + linear backoff

```go
// DefaultRetryPolicy: retry on timeout and 429 Too Many Requests
func DefaultRetryPolicy(resp *http.Response, err error) (shouldRetry bool, cleanErr error) {
    if err != nil {
        if netErr, ok := err.(net.Error); ok && netErr.Timeout() {
            return true, nil // network timeout — safe to retry
        }
        return false, err
    }
    return resp.StatusCode == http.StatusTooManyRequests, nil
}

// LinearBackoff: 100ms, 200ms, 300ms... capped at maxDuration
func LinearBackoff(base, max time.Duration) func(attempt int) time.Duration {
    return func(attempt int) time.Duration {
        d := base * time.Duration(attempt)
        if d > max {
            return max
        }
        return d
    }
}
```

### Pattern: Respect Retry-After header

```go
func retryAfterDuration(resp *http.Response) time.Duration {
    after := resp.Header.Get("Retry-After")

    // Form 1: integer seconds
    if secs, err := strconv.ParseInt(after, 10, 32); err == nil {
        return time.Duration(secs) * time.Second
    }
    // Form 2: HTTP-date (RFC1123)
    if when, err := time.Parse(time.RFC1123, after); err == nil {
        return time.Until(when)
    }
    return 0
}

// Use max of backoff and Retry-After
delay := max(backoff(attempt), retryAfterDuration(resp))

// Never sleep past context deadline
if dl, ok := ctx.Deadline(); ok && dl.Before(time.Now().Add(delay)) {
    return fmt.Errorf("%w: %w", errRetryFailed, context.DeadlineExceeded)
}

select {
case <-time.After(delay):
case <-ctx.Done():
    return ctx.Err()
}
```

### 预设失败策略
- Default 3 retries → enough for network blips; more than 3 usually means a logic error
- 429 with Retry-After → honor the header; exponential backoff without it risks getting banned
- Test retry logic → use `request.WithRetryNotAllowed(ctx)` in tests to get immediate failures

---

## 6. WebSocket Architecture

### When
Building WebSocket connections to exchange real-time feeds.

### Pattern: Manager + Connection Separation

Separate the orchestration layer (Manager) from the transport layer (Connection):

```go
// Manager: lifecycle, subscriptions, reconnection, data routing
type Manager struct {
    state             atomic.Uint32       // disconnected/connecting/connected
    connections       map[Connection]*ws  // connection → subscription mapping
    subscriptions     *subscription.Store
    DataHandler       *stream.Relay       // fan-in channel for all data
    Match             *Match              // request-response pairing
    Conn              Connection          // public (unauthenticated) connection
    AuthConn          Connection          // private (authenticated) connection

    // Exchange-provided callbacks
    connector         func() error
    Subscriber        func(subscription.List) error
    Unsubscriber      func(subscription.List) error
    GenerateSubs      func() (subscription.List, error)

    ShutdownC         chan struct{}
    Wg                sync.WaitGroup   // tracks reader goroutines
    TrafficAlert      chan struct{}     // size-1, non-blocking
    ReadMessageErrors chan error        // size-1, connection fault signal
}

// Connection: one WebSocket connection (gorilla ws underneath)
type Connection interface {
    Dial(ctx context.Context, dialer *gws.Dialer, headers http.Header, values url.Values) error
    ReadMessage() Response
    SendJSONMessage(ctx context.Context, epl request.EndpointLimit, payload any) error
    SendMessageReturnResponse(ctx context.Context, epl request.EndpointLimit, signature, request any) ([]byte, error)
    SetupPingHandler(epl request.EndpointLimit, handler PingHandler)
    Shutdown() error
    IsConnected() bool
}
```

### Pattern: ConnectionSetup — configure everything via a struct

When connecting, each connection is fully described by a setup struct rather than method parameters:

```go
type ConnectionSetup struct {
    URL           string
    Connector     func(ctx context.Context, conn Connection) error
    Authenticate  func(ctx context.Context, conn Connection) error
    Subscriber    func(ctx context.Context, conn Connection, subs subscription.List) error
    Handler       func(ctx context.Context, conn Connection, incoming []byte) error
    GenerateSubscriptions func() (subscription.List, error)
    RateLimit     *request.RateLimiterWithWeight
    ResponseMaxLimit time.Duration
}
```

### Pattern: Connect lifecycle

```go
func (e *Exchange) WsConnect() error {
    // 1. Dial TCP + upgrade to WebSocket
    if err := e.Websocket.Conn.Dial(ctx, &gws.Dialer{
        ReadBufferSize:  8192,
        WriteBufferSize: 8192,
    }, nil, nil); err != nil {
        return err
    }

    // 2. Setup keepalive before anything else
    e.Websocket.Conn.SetupPingHandler(request.Unset, websocket.PingHandler{
        UseGorillaHandler: true,         // Binance: use Gorilla's built-in pong
        MessageType:       gws.PongMessage,
        Delay:             9 * time.Minute,
    })

    // 3. Authenticate if private feed
    if e.Websocket.CanUseAuthenticatedEndpoints() {
        if err := e.wsAuthenticate(ctx); err != nil {
            return err
        }
    }

    // 4. Spawn reader goroutine
    e.Websocket.Wg.Add(1)
    go e.wsReadData(ctx)

    return nil
}

func (e *Exchange) wsReadData(ctx context.Context) {
    defer e.Websocket.Wg.Done()
    for {
        msg := e.Websocket.Conn.ReadMessage()
        if msg.Raw == nil {
            return // connection closed; shutdown triggered
        }
        // Signal traffic monitor (non-blocking)
        select {
        case e.Websocket.TrafficAlert <- struct{}{}:
        default:
        }
        if err := e.wsHandleData(ctx, msg.Raw); err != nil {
            e.Websocket.DataHandler.Send(ctx, err)
        }
    }
}
```

### Pattern: Request-Response pairing (Match system)

WebSocket is async. When you need to wait for a response to a specific request (e.g., subscribe confirmation, auth ack), use signature-based matching:

```go
// Sender side
resp, err := conn.SendMessageReturnResponse(ctx, wsRateLimit, requestID, payload)
// Blocks until a message with matching requestID arrives OR context expires

// Receiver side (in wsHandleData)
if conn.IncomingWithData(msg.RequestID, msg.Raw) {
    return nil // routed to waiting sender; don't process further
}
// Otherwise: regular market data, process normally
```

### 预设失败策略
- Don't use `AuthConn.Dial()` before authenticating → auth happens after Dial, not as a Dial option
- Data handler blocks → use a buffered fan-in channel (`Relay` with 5000 capacity); slow consumers cause backpressure; never block in the reader goroutine
- Multi-asset exchanges → use multi-connection management with separate connections per asset type and a `MessageFilter` field to route messages

---

## 7. Subscription Management

### When
Managing WebSocket channel subscriptions with state tracking.

### Pattern: State machine for subscriptions

Track each subscription through its lifecycle rather than using a simple bool:

```
Inactive → Subscribing → Subscribed → Unsubscribing → Unsubscribed
```

```go
// Before sending subscribe request
manager.AddSubscriptions(conn, subs...)          // → SubscribingState

// After exchange confirms
manager.AddSuccessfulSubscriptions(conn, subs...) // → SubscribedState

// Before unsubscribe
manager.RemoveSubscriptions(conn, subs...)        // → UnsubscribedState, removed from store
```

### Pattern: Subscription confirmation via Match

```go
func (e *Exchange) Subscribe(channels subscription.List) error {
    e.Websocket.AddSubscriptions(e.Websocket.Conn, channels...)

    req := SubscribeRequest{
        ID:     e.MessageID(),    // atomic counter
        Method: "SUBSCRIBE",
        Params: channels.QualifiedChannels(),
    }

    resp, err := e.Websocket.Conn.SendMessageReturnResponse(
        ctx, wsRateLimit, req.ID, req,
    )
    if err != nil {
        e.Websocket.RemoveSubscriptions(e.Websocket.Conn, channels...)
        return err
    }

    // null response = success (Binance pattern)
    if string(resp) == "null" {
        e.Websocket.AddSuccessfulSubscriptions(e.Websocket.Conn, channels...)
    }
    return nil
}
```

### Pattern: Chunking subscriptions by payload size

Some exchanges reject subscription requests over a byte limit:

```go
const maxPayloadBytes = 4096

func (e *Exchange) chunkSubscriptions(subs subscription.List) [][]Subscription {
    var chunks [][]Subscription
    var current []Subscription
    var size int

    for _, sub := range subs {
        encoded, _ := json.Marshal(sub)
        if size+len(encoded) > maxPayloadBytes && len(current) > 0 {
            chunks = append(chunks, current)
            current = nil
            size = 0
        }
        current = append(current, sub)
        size += len(encoded)
    }
    if len(current) > 0 {
        chunks = append(chunks, current)
    }
    return chunks
}
```

### 预设失败策略
- Reconnection loses subscriptions → call `GenerateSubs()` fresh on every reconnect; subscriptions may have changed
- Over-subscribing single connection → set `MaxSubscriptionsPerConnection` and scale to multiple connections
- Duplicate subscriptions → the subscription store deduplicates by channel identity; check state before subscribing

---

## 8. Keepalive & Reconnection

### When
Maintaining stable WebSocket connections through network hiccups and exchange-side timeouts.

### Pattern: Two-mode ping handler

```go
// Mode 1: Gorilla automatic (server pings us, we pong)
conn.SetupPingHandler(rateLimit, PingHandler{
    UseGorillaHandler: true,
    MessageType:       gws.PongMessage,
    Delay:             9 * time.Minute, // Binance
})

// Mode 2: Client-initiated ping (we ping the server periodically)
conn.SetupPingHandler(rateLimit, PingHandler{
    UseGorillaHandler: false,
    MessageType:       gws.TextMessage,
    Message:           []byte("ping"),
    Delay:             20 * time.Second, // OKX
})
```

### Pattern: Traffic-based reconnect

Use a non-blocking channel to signal message receipt. A separate goroutine watches for silence:

```go
// In reader goroutine — non-blocking signal on every message
select {
case m.TrafficAlert <- struct{}{}:
default: // don't block if monitor hasn't consumed previous signal
}

// Traffic monitor goroutine (NOT in WaitGroup — survives reconnect)
func (m *Manager) monitorTraffic(ctx context.Context, timeout time.Duration) {
    timer := time.NewTimer(timeout)
    defer timer.Stop()
    for {
        select {
        case <-m.ShutdownC:
            return
        case <-m.TrafficAlert:
            timer.Reset(timeout) // reset on every message
        case <-timer.C:
            // No traffic for `timeout` — reconnect
            go m.Shutdown()
            return
        }
    }
}
```

### Pattern: Graceful shutdown

```go
// Shutdown sequence:
// 1. Close ShutdownC to broadcast to all goroutines
// 2. Close underlying WebSocket connections
// 3. Wait for reader goroutines to exit (Wg.Wait)
// 4. Monitor goroutines detect ShutdownC and exit on their own

func (m *Manager) Shutdown() {
    close(m.ShutdownC)
    for conn := range m.connections {
        conn.Shutdown()
    }
    m.Wg.Wait() // wait for readers

    // Re-initialize ShutdownC for next connect
    m.ShutdownC = make(chan struct{})
}
```

### 预设失败策略
- `close(ShutdownC)` called twice → protect with `sync.Once` or atomic flag; double-close panics
- Traffic timeout too aggressive → set it to `2× expected heartbeat interval`; exchange-specific heartbeat docs are the source of truth
- Reconnect loop spinning → add exponential backoff between reconnect attempts; a tight loop can exhaust rate limits

---

## 9. Orderbook Real-time Management

### When
Maintaining an accurate real-time orderbook from WebSocket incremental updates.

### Pattern: Snapshot + Incremental update sync

The correct sequence to bootstrap a real-time orderbook:

```go
// Step 1: Subscribe to WS depth stream — buffer updates immediately
// Step 2: Fetch REST snapshot
snapshot, err := e.GetOrderbook(ctx, pair)

// Step 3: Load snapshot into depth, discarding buffered updates before snapshot's UpdateID
depth.LoadSnapshot(&orderbook.Book{
    Bids:         snapshot.Bids,
    Asks:         snapshot.Asks,
    LastUpdateID: snapshot.LastUpdateID,
    RestSnapshot: true, // flag: this is a REST baseline
})

// Step 4: Apply buffered WS updates where UpdateID > snapshot.LastUpdateID
// Step 5: Apply all subsequent WS updates incrementally
```

### Pattern: ActionType for update operations

Different exchanges signal orderbook changes differently. Normalize to an action enum:

```go
type ActionType uint8
const (
    UnknownAction      ActionType = iota // default: update by price (insert-or-update)
    InsertAction                         // insert new level
    UpdateOrInsertAction                 // upsert
    UpdateAction                         // update existing; ignore if price not found
    DeleteAction                         // remove level (amount=0 typically signals this)
)

// Apply update
func applyUpdate(depth *Depth, update Update) {
    switch update.Action {
    case DeleteAction:
        depth.deleteByPrice(update.Price) // or deleteByID
    case InsertAction:
        depth.insert(Level{Price: update.Price, Amount: update.Amount})
    default: // UnknownAction, UpdateOrInsertAction
        depth.updateByPrice(Level{Price: update.Price, Amount: update.Amount})
    }
}
```

### Pattern: Orderbook buffering for atomic updates

Don't apply updates one-by-one during high-frequency periods. Buffer and apply in batches for consistency:

```go
type orderbookHolder struct {
    depth  *Depth
    buffer []orderbook.Update
}

func (o *Orderbook) Update(u *orderbook.Update) error {
    holder := o.ob[u.PairAsset]
    holder.buffer = append(holder.buffer, *u)

    if len(holder.buffer) >= o.bufferLimit {
        // Sort by timestamp or update ID, then apply all atomically
        sort.SliceStable(holder.buffer, func(i, j int) bool {
            return holder.buffer[i].UpdateID < holder.buffer[j].UpdateID
        })
        for _, buffered := range holder.buffer {
            holder.depth.ProcessUpdate(&buffered)
        }
        holder.buffer = holder.buffer[:0]
    }
    return nil
}
```

### Orderbook validation invariants

Always validate after applying updates:

- **Bids**: strictly descending by price (highest bid first)
- **Asks**: strictly ascending by price (lowest ask first)
- **Bid price < Ask price**: no crossed book
- **Amount > 0** for all levels (zero-amount = delete signal, shouldn't remain)
- **Checksum match** if exchange provides one (Kraken, OKX)

### 预设失败策略
- Crossed orderbook → indicates missed or out-of-order update; re-fetch REST snapshot and resync
- "Last update ID mismatch" → the buffered update sequence has a gap; resync from REST snapshot
- Not buffering during initial REST fetch → can miss updates; always start WS subscription before the REST call

---

## 10. Financial Data Types

### When
Unmarshaling JSON from exchange APIs that use strings for numbers, non-standard timestamp formats, or exchange-specific symbol strings.

### Pattern: `types.Number` — handles string or numeric JSON prices

Exchanges inconsistently represent prices/amounts as JSON strings or numbers. A custom type handles both:

```go
type Number float64

func (n *Number) UnmarshalJSON(data []byte) error {
    // Handle null
    if string(data) == "null" {
        return nil
    }
    // Remove quotes if string
    s := strings.Trim(string(data), `"`)
    f, err := strconv.ParseFloat(s, 64)
    if err != nil {
        return err
    }
    *n = Number(f)
    return nil
}

func (n Number) Float64() float64 { return float64(n) }
func (n Number) Int64() int64     { return int64(n) }
```

For precision-critical financial math, use `shopspring/decimal` via `n.Decimal()` rather than the `float64` value.

### Pattern: `types.Time` — handles unix ms/ns/s + ISO strings

Exchange timestamps come in many formats:

```go
func (t *Time) UnmarshalJSON(data []byte) error {
    s := strings.Trim(string(data), `"`)
    // Detect by digit count
    switch len(s) {
    case 10: // Unix seconds
        epoch, _ := strconv.ParseInt(s, 10, 64)
        *t = Time(time.Unix(epoch, 0))
    case 13: // Unix milliseconds
        epoch, _ := strconv.ParseInt(s, 10, 64)
        *t = Time(time.UnixMilli(epoch))
    case 16: // Unix microseconds
        epoch, _ := strconv.ParseInt(s, 10, 64)
        *t = Time(time.UnixMicro(epoch))
    default: // ISO 8601 / RFC3339
        parsed, _ := time.Parse(time.RFC3339, s)
        *t = Time(parsed)
    }
    return nil
}
```

### Pattern: currency.Pair auto-detection from JSON

Pairs arrive as exchange-specific strings ("BTCUSDT", "BTC-USDT", "BTC_USD"). Auto-detect delimiter by scanning for punctuation:

```go
func (p *Pair) UnmarshalJSON(data []byte) error {
    s := strings.Trim(string(data), `"`)
    // Detect delimiter from first punctuation character
    for _, ch := range s {
        if ch == '-' || ch == '_' || ch == '/' || ch == ':' {
            // Split on this delimiter
            parts := strings.SplitN(s, string(ch), 2)
            p.Base = currency.NewCode(parts[0])
            p.Quote = currency.NewCode(parts[1])
            p.Delimiter = string(ch)
            return nil
        }
    }
    // No delimiter — ambiguous without a symbol table lookup
    return fmt.Errorf("cannot auto-detect delimiter in %q; use MatchSymbol()", s)
}
```

### Pattern: Composite key for data storage

All market data (tickers, orderbooks, trades) is keyed by the same composite:

```go
type ExchangeAssetPair struct {
    Exchange string
    Asset    asset.Item
    Base     *currency.Item // pointer, not string — enables O(1) comparison
    Quote    *currency.Item
}
```

Using `*currency.Item` pointers rather than strings means equality checks are pointer comparisons — faster than string comparison in hot paths.

### 预设失败策略
- Float64 for prices → use `shopspring/decimal` for all monetary arithmetic; `float64` accumulates rounding errors
- Custom timestamp parser panics on empty string → check `len(data) == 0` or `data == "null"` before parsing
- Symbol ambiguity without delimiter → always use the exchange's `MatchSymbolWithAvailablePairs()` method to resolve to canonical pairs; don't try to parse raw symbols directly
