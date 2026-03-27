# 价格源选型知识库 v1.0
# 最后更新：2026-03-27 | 基于实际 API 调用验证

> **目录**
> 1. [已验证价格源档案](#1-已验证价格源档案)
> 2. [价格源能力矩阵](#2-价格源能力矩阵)
> 3. [场景选型决策树](#3-场景选型决策树)
> 4. [调研经验教训（防坑指南）](#4-调研经验教训防坑指南)
> 5. [API 接入快速参考](#5-api-接入快速参考)
> 6. [风险清单](#6-风险清单)

---

## 1. 已验证价格源档案

### 1.1 Pyth Network

| 字段 | 值 |
|------|---|
| **类型** | 去中心化 Pull Oracle |
| **官网** | https://pyth.network |
| **API 基础** | https://hermes.pyth.network/v2/ |
| **费用** | Off-chain 完全免费；On-chain 仅 Gas（~$0.0001/次）|
| **Feed 数量** | 2,958 条（截至 2026-03-27）|
| **发布者数量** | 120+ 机构（Cboe、Coinbase、Virtu、Revolut 等）|
| **更新频率** | ~400ms（Hermes 链下）；链上 <100ms |
| **速率限制** | 30 req/10s/IP（免费）；超限封禁 60s |

**⚠️ 关键认知：美股资产多 Feed 架构**

Pyth 对美股（AAPL、SPY 等）不是单一 Feed，而是**按交易时段拆分为 4 个独立 Feed**：

| Feed 类型 | 活跃时段（ET） | 非活跃时段行为 |
|----------|--------------|-------------|
| Regular | 09:30–16:00 周一至五 | `publishTime` 冻结在收盘时刻 |
| Pre-Market | 04:00–09:30 周一至五 | 同上 |
| Post-Market | 16:00–20:00 周一至五 | 同上 |
| Overnight | 20:00–04:00（次日）周一至五 | 同上 |

**调用方必须**：
1. 枚举所有相关 Feed ID（通过 `/v2/price_feeds?query=AAPL&asset_type=equity` 获取）
2. 对每个 Feed 检查 `publishTime` 新鲜度
3. 当前活跃 Feed 的 σ/μ（置信区间/价格比）远低于非活跃 Feed

```bash
# 获取 AAPL 所有相关 Feed
curl "https://hermes.pyth.network/v2/price_feeds?query=AAPL&asset_type=equity"

# 获取价格（替换为实际 feed_id）
curl "https://hermes.pyth.network/v2/updates/price/latest?ids[]=<feed_id>&parsed=true"
```

**典型价差（2026-03-27 夜盘观测）**：
```
Pre-Market 末价 $251.99 → Regular 收盘 $253.03 → Post-Market 末价 $254.82 → Overnight 当前 $254.55
跨时段价差：~$2.83（约 1.12%）
```

---

### 1.2 Hyperliquid

| 字段 | 值 |
|------|---|
| **类型** | 链上 DEX Oracle（HyperBFT L1）|
| **官网** | https://hyperliquid.xyz |
| **API 基础** | https://api.hyperliquid.xyz/info |
| **费用** | 完全免费，无 API Key |
| **验证者数量** | 24 个活跃节点 |
| **更新频率** | 5s（Oracle Price）；WebSocket ≥0.5s |
| **资产覆盖** | **仅加密货币永续合约** |

**⚠️ 关键认知：美股资产无效**

- Hyperliquid **不提供任何官方美股数据**
- 存在社区部署的同名 Token（如 AAPL index 413），特征：
  - `isCanonical: false`
  - `deployerTradingFeeShare: 1.0`（100% 手续费归部署者——欺诈信号）
  - `dayNtlVlm: 0.0`（零交易量）
  - 价格完全不追踪真实资产（实测 AAPL Token markPx = $0.049，非 $254）
- **禁止将此类 Token 价格用于任何真实产品定价**

```bash
# 获取所有加密永续合约价格
curl -X POST https://api.hyperliquid.xyz/info \
  -H "Content-Type: application/json" \
  -d '{"type":"metaAndAssetCtxs","dex":"xyz"}'
```

---

### 1.3 Massive

| 字段 | 值 |
|------|---|
| **类型** | 商业金融数据平台 |
| **正确域名** | https://massive.com（**注意**：massive.finance 域名已失效）|
| **API 基础** | https://api.massive.com/v2/ |
| **SLA** | 99.99%，70M msg/s |
| **知名客户** | Google、Revolut、The Motley Fool、Stanford University |

**定价层级（2026-03-27 实测，原始 JSON 从页面 JS bundle 提取）**：

| 档位 | 月付 | 年付/月 | 关键限制 |
|------|------|---------|---------|
| Free | $0 | $0 | 5 req/min；EOD 数据；2年历史；无快照/实时 Quotes |
| Starter | $29 | $24 | 无限 req；5年历史；秒级 OHLCV；快照 |
| Pro | $79 | $64 | 无限 req；10年历史；全功能；仍无 L1 NBBO Quotes |
| Unlimited | $199 | $160 | L1 NBBO 实时 bid/ask；20+年历史；财务报表 |
| Business | 定制 | — | 专有 FMV；企业 SLA |

**⚠️ 关键认知：定价页面是动态渲染**
- `https://massive.com/pricing` 使用 Next.js，curl 只能获取 JS bundle，无法直接读取价格
- 实际定价数据藏在 JS bundle 中的 `amount` 字段（单位：美分）：2900/$29、7900/$79、19900/$199
- 需用 `grep -oP '"amount":\K[0-9]+'` 提取，或使用 Playwright 截图

---

### 1.4 Tiger Brokers OpenAPI（老虎证券）

| 字段 | 值 |
|------|---|
| **类型** | 合规持牌券商 OpenAPI |
| **持牌地区** | 新加坡 MAS、美国 FINRA+SEC、香港 SFC、澳大利亚 ASIC |
| **文档** | https://docs.itigerup.com |
| **费用** | 交易免费；行情需独立购买（Tiger Trade App → 行情权限商店）|
| **认证** | RSA 私钥 + Tiger ID |
| **数据来源** | Nasdaq Basic（L1）/ Nasdaq TotalView（L2）+ 各交易所官方 SIP |

**⚠️ 核心约束：单设备行情独占**

行情权限同一时刻**仅支持一台设备**。多实例部署场景下，所有实例会互相抢占。

```python
# 生产必须实现的抢占逻辑
client.grab_quote_permission()  # 在每次初始化时调用
```

**⚠️ 重要区分：Tiger Brokers ≠ 项目内 mmgateway**

| 对比维度 | Tiger Brokers OpenAPI | 项目内 mmgateway |
|---------|----------------------|----------------|
| 本质 | 外部合规券商 API | 内部 K8s 代理服务 |
| 地址 | https://openapi.tigerbrokers.com | http://mmgateway-eks-*.cpt-prod01 |
| 认证 | RSA 私钥 + Tiger ID | 内部服务无需认证 |
| 夜盘价格 | 综合账户支持盘前/盘后 | `latestPrice` 已注释（夜盘无效）|

---

## 2. 价格源能力矩阵

| 维度 | Pyth | Hyperliquid | Massive | Tiger Brokers |
|------|------|-------------|---------|---------------|
| 加密货币 | ✅ 1,500+ Feed | ✅ 仅永续合约 | ✅ 含加密 | ❌ |
| 美股实时 | ✅（4 Feed/股）| ❌ | ✅（$29+）| ✅（需行情权限）|
| 美股 L2 深度 | ❌ | ❌ | ✅（$199 Unlimited）| ✅（Nasdaq TotalView）|
| 期权 Greeks | ❌ | ❌ | ✅（$199）| ✅（L1 期权权限）|
| 外汇（FX）| ✅ ~30 对 | ❌ | ✅ 1,750+ 对 | ✅（多交易所）|
| 商品（黄金/原油）| ✅ ~20 个 | ❌ | ✅ CME 4 交易所 | ✅ COMEX/NYMEX |
| 7×24 | 加密 ✅；TradFi 依时段 | 加密 ✅ | 加密 ✅；FX 24/5 | ❌ 仅交易日+盘前/后 |
| 盘前/盘后 | ✅（独立 Feed）| N/A | ✅（4AM-8PM EST）| ✅（综合账户）|
| 链上集成 | ✅ 80+ 链 | ✅ HyperEVM | ❌ | ❌ |
| 免费实时访问 | ✅ | ✅ | ❌（Free 层 EOD）| ❌（需行情购买）|
| API 认证 | 无 | 无 | API Key | RSA 私钥 |
| 历史数据 | 数天（Benchmarks）| 最近 5,000 条 K线 | 2~20+ 年（按档位）| 10 年 1 分 K |
| Uptime SLA | 99.9%+ | 无公开 SLA | **99.99%** | 多地合规，无公开 SLA |

---

## 3. 场景选型决策树

```
需要美股数据？
├─ YES → 盘中实时 bid/ask 是核心需求？
│         ├─ YES → Tiger Brokers（主）+ Pyth Overnight Feed（非交易日备份）
│         └─ NO  → 量化回测 / 期权研究？
│                   ├─ YES → Massive $79（OHLCV）或 $199（含 Greeks + NBBO）
│                   └─ NO  → Pyth（免费，链上 DeFi 场景）
│
└─ NO → 需要加密货币数据？
          ├─ YES → 链上 DeFi / 智能合约定价？
          │         ├─ YES → Pyth（首选，80+ 链原生，免费）
          │         └─ NO  → 中心化平台？
          │                   → Hyperliquid Oracle（加密专项，免费元验证层）
          │                   + Pyth 双重校验（小币种覆盖）
          └─ NO → FX / 商品？
                    → Massive $29（FX 1,750+ 对）
                    或 Tiger Brokers（CME/COMEX 期货行情）
```

**非交易日 / 停牌应急方案**（必须配置）：

| 主数据源 | 非交易日备份 | 配置要点 |
|---------|-----------|---------|
| Tiger Brokers | Pyth Overnight Feed | 监控 `publishTime` 新鲜度 |
| Tiger Brokers | Massive Free（EOD）| 仅限 T 日收盘价，非实时 |
| Massive Starter | Pyth（同品种 Feed）| 注意时段切换逻辑 |

---

## 4. 调研经验教训（防坑指南）

### 坑 1：域名混淆（Massive）
- ❌ `massive.finance` — 域名已失效（parked/expired）
- ❌ `massivex.com` — 无关平台
- ❌ `massivex.io` — 连接拒绝
- ✅ `massive.com` — 正确官方域名

### 坑 2：动态渲染页面 curl 无效
以下页面类型 curl 无法获取真实数据：
- Next.js / Nuxt.js 渲染的定价页（如 massive.com/pricing）
- React SPA（路由跳转后的内容）
- 需要登录才能显示的权限信息

**处理方法**：
1. 先 curl，检测是否含 `__NEXT_DATA__` / `_next/static` / `ReactDOM`
2. 若存在，对静态 JS bundle 用正则提取嵌入数据（`grep -oP '"amount":\K[0-9]+'`）
3. 若无法提取，降级到 Playwright 截图 + 视觉分析

### 坑 3：Pyth Feed ID 错误
- 初始使用 `49f6b65a...`（错误）→ 应为 `49f6b65c...`（正确 Regular Feed）
- 始终通过 `/v2/price_feeds?query=AAPL&asset_type=equity` 动态获取当前有效 Feed ID
- Feed ID 可能随 Pyth 版本变化，不可硬编码

### 坑 4：虎 API 403 / 重定向
- `itiger.com` 系列域名返回 403 或跳转至 App 下载页
- 正确文档地址：
  - 新版：`https://docs.itigerup.com`
  - 旧版：`https://quant.itigerup.com/openapi/zh/`

### 坑 5：Hyperliquid 非官方 Token 混淆
- 任何 `isCanonical: false` 的 Token 均不代表真实资产价格
- `deployerTradingFeeShare: 1.0` 是典型欺诈性命名 Token 标志
- 调研前先过滤：`[t for t in tokens if t['isCanonical']]`

### 坑 6：时区混淆（ET vs UTC）
- 所有美股时段描述均以 **ET（美东时间）** 为基准
- 服务器时间通常为 UTC，换算：
  - ET（EST） = UTC - 5（冬令时）
  - ET（EDT） = UTC - 4（夏令时，3月第二个周日到11月第一个周日）
- Pyth `publishTime` 为 Unix 时间戳（UTC），本地化时注意时区

---

## 5. API 接入快速参考

### Pyth — 获取美股所有 Feed
```bash
# Step 1: 枚举 Feed ID
curl -s "https://hermes.pyth.network/v2/price_feeds?query=AAPL&asset_type=equity" | \
  python3 -c "import json,sys; [print(f['id'][:8], f['attributes']['description'], f['attributes'].get('schedule','')) for f in json.load(sys.stdin)]"

# Step 2: 获取实时价格
curl -s "https://hermes.pyth.network/v2/updates/price/latest?ids[]=<feed_id>&parsed=true" | \
  python3 -c "
import json, sys, datetime
d = json.load(sys.stdin)
for p in d['parsed']:
    price = int(p['price']['price']) * (10 ** p['price']['expo'])
    conf  = int(p['price']['conf'])  * (10 ** p['price']['expo'])
    age   = datetime.datetime.now(datetime.timezone.utc).timestamp() - p['price']['publish_time']
    print(f\"\${price:.4f} ±\${conf:.4f}  age={age:.0f}s  {'LIVE' if age<10 else 'STALE'}\")
"
```

### Hyperliquid — 加密永续合约价格
```bash
curl -s -X POST https://api.hyperliquid.xyz/info \
  -H "Content-Type: application/json" \
  -d '{"type":"metaAndAssetCtxs","dex":"xyz"}' | \
  python3 -c "
import json, sys
data = json.load(sys.stdin)
meta, ctxs = data[0], data[1]
for i, asset in enumerate(meta['universe'][:5]):  # 前5个合约
    ctx = ctxs[i]
    print(asset['name'], 'oracle:', ctx['oraclePx'], 'mark:', ctx['markPx'])
"
```

### Massive — 获取快照（需 API Key）
```bash
curl -s "https://api.massive.com/v2/snapshot/locale/us/markets/stocks/tickers/AAPL" \
  -H "Authorization: Bearer <API_KEY>"
```

### Tiger Brokers — Python SDK
```python
from tigeropen.tiger_open_config import TigerOpenClientConfig
from tigeropen.quote.quote_client import QuoteClient

config = TigerOpenClientConfig()
config.tiger_id = 'YOUR_TIGER_ID'
config.private_key = 'YOUR_RSA_PRIVATE_KEY'
client = QuoteClient(config)

client.grab_quote_permission()          # 多实例必须先抢占
briefs = client.get_stock_briefs(['AAPL', 'SPY'])
```

---

## 6. 风险清单

| 风险 | 受影响源 | 严重度 | 缓解措施 |
|------|---------|--------|---------|
| 非活跃时段 publishTime 冻结 | Pyth（TradFi 资产）| 高 | 实现 `getPriceNoOlderThan(300)` 检查 |
| 非官方 Token 价格欺诈 | Hyperliquid | 极高 | 仅使用 `isCanonical: true` 资产 |
| 单设备行情抢占 | Tiger Brokers | 高 | 实现 `grab_quote_permission()` 主实例逻辑 |
| 定价页动态渲染无法爬取 | Massive、多数现代平台 | 中 | Playwright 截图降级 + JS bundle 提取 |
| Free 层 EOD 限制 | Massive | 中 | 生产环境使用 $29+ 订阅 |
| Wormhole 跨链依赖 | Pyth（链上）| 中 | 多 Oracle 交叉验证 |
| 订阅额度门槛 | Tiger Brokers | 中 | 确保账户资产 ≥ 所需等级 |
| 速率超限封禁 | Pyth Hermes | 低 | 使用 SSE 流替代轮询 |
| Flash Loan 攻击 | Pyth（链上）| 中 | 强制最小持仓时间 + 延迟结算 |
