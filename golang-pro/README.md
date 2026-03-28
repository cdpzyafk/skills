# golang-pro

面向 Go 1.21+ 的 AI 编程技能，覆盖代码设计、错误处理、并发、性能优化、调试全生命周期。基于 Google、Uber、Effective Go 权威风格指南提炼，配备渐进式披露结构，按需加载详细参考。

---

## 安装

### 前提条件

安装 [Claude Code](https://claude.ai/code)，技能通过其 `Skill` 工具系统加载。

### 安装技能

```bash
# 将技能目录放入 Claude Code 的技能搜索路径
cp -r golang-pro ~/.claude/skills/

# 或者 clone 到技能目录
git clone git@github.com:cdpzyafk/golang-pro.git ~/.claude/skills/golang-pro
```

技能加载后，在技能列表中出现：
```
golang-pro: Use when building Go applications requiring concurrent programming...
```

### 依赖工具

技能中的命令和建议依赖以下工具，按需安装：

| 工具 | 用途 | 安装 |
|------|------|------|
| `goimports` | 格式化代码 + 管理 import | `go install golang.org/x/tools/cmd/goimports@latest` |
| `golangci-lint` | 综合 linter 套件 | `go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest` |
| `staticcheck` | 额外静态分析 | `go install honnef.co/go/tools/cmd/staticcheck@latest` |
| `dlv` (Delve) | Go 交互式调试器 | `go install github.com/go-delve/delve/cmd/dlv@latest` |
| `go.uber.org/goleak` | goroutine 泄漏检测 | `go get go.uber.org/goleak` (加入 go.mod) |
| `go.uber.org/atomic` | 类型安全的原子操作 | `go get go.uber.org/atomic` |
| `github.com/shopspring/decimal` | 金融场景精确小数 | `go get github.com/shopspring/decimal` |
| `golang.org/x/sync/errgroup` | 并发任务协同 + 优雅关机 | `go get golang.org/x/sync` |
| `pkgsite` | 本地预览 godoc | `go install golang.org/x/pkgsite/cmd/pkgsite@latest` |

> 日常开发只需 `goimports` + `golangci-lint`。其他工具在对应场景（调试、性能分析、金融系统）时按需安装。

---

## 技能构成

```
golang-pro/
├── SKILL.md                      # 入口：核心规则 + 渐进式披露导航表
└── references/
    ├── foundation.md             # 风格、命名、包设计、文档、slog 日志
    ├── error-handling.md         # 错误返回、包装、类型选择、控制流
    ├── concurrency.md            # goroutine 生命周期、mutex、channel、context、优雅关机
    ├── design-patterns.md        # 接口设计、functional options、防御性编程
    ├── testing-quality.md        # 测试编写、代码审查清单、linting 配置
    ├── performance.md            # 数据结构、切片/map 预分配、热路径优化
    └── debugging.md              # race detector、pprof、trace、Delve、goroutine dump
```

### 三层加载机制

```
Layer 1  SKILL.md 元数据 (name + description)
         ↓ 始终在上下文中，约 100 词
Layer 2  SKILL.md 正文 (Core Rules + 导航表)
         ↓ 技能触发时自动加载
Layer 3  references/*.md (按需加载)
         ↓ 只读取当前任务相关的那一个
```

**优点**：高频规则（命名、错误处理、context）始终可见；低频细节（pprof 用法、iota 陷阱）只在需要时消耗上下文。

### 渐进式披露导航表（SKILL.md 核心）

| 场景 | 加载 |
|------|------|
| 命名、风格、导入、包设计、文档、slog 日志 | `references/foundation.md` |
| 错误处理、控制流、guard clause | `references/error-handling.md` |
| goroutine、channel、mutex、context、优雅关机 | `references/concurrency.md` |
| 接口设计、functional options、防御性编程 | `references/design-patterns.md` |
| 编写测试、代码审查、linting 配置 | `references/testing-quality.md` |
| 数据结构、切片/map、性能调优 | `references/performance.md` |
| 数据竞争、pprof、goroutine dump、Delve、go vet | `references/debugging.md` |

---

## 使用方法

### 自动触发

任何 Go 相关任务都会自动触发此技能：

```
"帮我实现一个带超时的 HTTP 客户端"
"review 这段 Go 代码"
"这个 goroutine 为什么会泄漏"
"如何优化这个切片操作的性能"
```

### 工作流

**1. 代码设计**

技能加载后，Core Rules 立即生效：
```go
// 每行代码自动遵守：
// ✓ 构造函数返回 concrete type，不返回 interface
// ✓ I/O 函数第一个参数是 ctx context.Context
// ✓ 接口在消费方包定义，不在实现方
```

需要深入设计指导时，AI 会主动加载对应 reference 文件。

**2. 代码编写**

参考 `SKILL.md` 中的预设失败策略直接作决定，无需查文档：

```
应该用 async 还是 sync？  → 同步优先，调用方决定是否加并发
error 在哪里打日志？      → 只在最顶层 handler，helpers 只 return
性能问题怎么看？          → 先跑 benchmark，p99 < SLA 则停手
```

**3. 并发 / 优雅关机**

遇到 goroutine、signal 处理等需求时，加载 `references/concurrency.md`，内含完整模板：

```go
// 标准优雅关机模板（来自 concurrency.md）
ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
defer stop()
if err := run(ctx); err != nil {
    log.Fatal(err)
}
```

**4. 性能优化**

加载 `references/performance.md` 获取热路径优化决策：

```bash
# 技能规则：无 benchmark 不优化
go test -bench=BenchmarkFoo -benchmem -count=5
go tool pprof -http=:8080 cpu.out  # 找最宽的 box
```

**5. 调试**

加载 `references/debugging.md` 获取症状→工具→命令速查表：

| 症状 | 命令 |
|------|------|
| 疑似数据竞争 | `go test -race ./...` |
| goroutine 泄漏 | `defer goleak.VerifyNone(t)` |
| CPU 瓶颈 | `go test -bench=. -cpuprofile=cpu.out` |
| 进程挂起/死锁 | `kill -SIGQUIT <pid>` |

**6. 金融 / 交易系统**

`SKILL.md` 内置 Domain-Specific 章节，无需额外加载：

```go
// 技能内置规则：货币用 decimal，不用 float64
import "github.com/shopspring/decimal"

func (p *Portfolio) Value(price decimal.Decimal) decimal.Decimal {
    if price.IsZero() || price.IsNegative() {
        return decimal.Zero
    }
    return p.quantity.Mul(price)
}
```

---

## 与其他 go-* 技能的关系

`golang-pro` 是 **主入口**，覆盖 80% 的日常场景。独立的 `go-*` 技能（`go-concurrency`、`go-error-handling` 等）是深度参考，当需要某个主题的完整原始说明时使用。

```
日常任务         →  golang-pro（自动触发）
某主题的完整说明  →  对应的 go-* 技能（手动调用）
```
