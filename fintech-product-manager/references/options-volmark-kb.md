# 期权波动率标记（Vol Mark）知识库

> 来源：`option-feature-engineering` 项目实战提炼（加密 + 美股期权）

本文件记录**期权隐含波动率曲面标定**的完整知识，包括模型原理、参数含义、市场差异、常见误区。用于评审期权产品设计文档、vol mark 参数校准、以及期权类理财产品可行性分析。

---

## 目录

1. [核心概念：Moneyness / TTM / Vol Surface](#1-核心概念)
2. [JWSS7 波动率曲面模型](#2-jwss7-模型)
3. [Vol Mark 拟合流程](#3-vol-mark-拟合流程)
4. [加密资产 vs 美股期权的差异](#4-加密资产-vs-美股期权)
5. [到期日规则](#5-到期日规则)
6. [执行价网格设计](#6-执行价网格设计)
7. [Vol Surface 套利校验](#7-vol-surface-套利校验)
8. [常见误区](#8-常见误区)

---

## 1. 核心概念

### Moneyness（价值度）

**Moneyness = K / S**，执行价除以现货价，衡量期权距离平值的位置。

| Moneyness | 含义 | 叫法 |
|-----------|------|------|
| < 1.0 | 执行价低于现货 | OTM put / ITM call |
| = 1.0 | 执行价等于现货 | ATM（平值） |
| > 1.0 | 执行价高于现货 | OTM call / ITM put |

标准化 log-moneyness：`z = log(K/F) / (atmfvol × sqrt(tau))`，是 vol 曲面的自变量。

### TTM（Time to Maturity，到期时间）

期权定价的时间维度，**必须与市场年化基准一致**：

| 资产类型 | 基准 | 年化秒数 |
|---------|------|---------|
| 加密资产（7×24） | 365.25 天连续 | 31,557,600 |
| 美股（Pionex 5×24） | 252 交易日 × 24h | 21,772,800 |

计算公式：`TTM = (expiry - now).total_seconds() / secs_per_year`

**误区**：用同一个年化常数处理加密和美股会导致 TTM 系统性偏差，进而影响 vol smile 的 z-score 计算和 Greeks。

### Vol Surface（波动率曲面）

以 **Moneyness** 为 X 轴、**TTM** 为 Y 轴、**Implied Vol** 为 Z 轴的三维曲面。

```
Implied Vol
    │        *           *       ← 两端 vol 高（smile）
    │           *     *
    │              *             ← ATM vol 最低
    └─────────────────────────── Moneyness
         0.8  0.9  1.0  1.1  1.2
```

**Skew**（偏斜）：
- 负 skew（`skew < 0`）：put 端 vol 更高，典型于**股票**市场（市场对下跌保护需求更强）
- 正 skew：call 端 vol 更高，典型于**大宗商品**（担忧供给冲击）

---

## 2. JWSS7 模型

7 参数 vol 曲面模型，参数 `[atmfvol, skew, smile, put_slope, call_slope, ap, ac]`：

| 参数 | 含义 | 典型范围 | 产品含义 |
|------|------|---------|---------|
| `atmfvol` | ATM 波动率（平值隐含 vol） | 0.3–1.5 | 直接决定平值期权的权利金水平 |
| `skew` | vol 曲线的左右不对称性 | -0.3–0.3 | 负值 = put 贵，正值 = call 贵 |
| `smile` | vol 曲线的凸性（微笑幅度） | -0.1–0.5 | 控制 OTM 期权溢价 |
| `put_slope` | put 端 wing 斜率 | 0.1–1.0 | 深度 OTM put 的溢价速率 |
| `call_slope` | call 端 wing 斜率 | -0.3–0.5 | 深度 OTM call 的溢价速率 |
| `ap` | put wing 的幂次平滑系数 | -0.5–1.0 | 控制极端 put 斜率是否爆炸 |
| `ac` | call wing 的幂次平滑系数 | -0.5–1.0 | 控制极端 call 斜率是否爆炸 |

**vol smile 计算流程**：

```
z = log(K/F) / (atmfvol × sqrt(tau))     ← 标准化 log-moneyness
B = (put_slope + 2×skew) / (call_slope + put_slope)
A = (put_slope + 2×skew)(call_slope - 2×skew) / (skew² + smile) / 2
X = B × exp(C × zC) + (1-B) × exp(-P × zP)   ← wing 混合
vol = atmfvol × sqrt(max(1 + A × ln(X), 0))
```

**VolSpread（买卖价差）**：固定为 `atmfvol × 10%`，反映做市商对冲成本。

---

## 3. Vol Mark 拟合流程

### 数据窗口参数

| 参数 | 含义 | 典型值 |
|------|------|--------|
| `lag_size` | 窗口距今的偏移天数 | 30（稳定性优先）/ 0（实时性优先） |
| `expiry_size` | 历史数据窗口长度（天） | 30–60 |

```
时间轴示例（lag=30, expiry=60）：
  last_obs - 90d          last_obs - 30d       last_obs
       ├──────── 60天数据 ─────────┤← 30天 lag →│
    starttime               endtime
```

- **lag_size=30**：使用30天前结束的历史窗口，参数稳定，适合生产守护进程（每30分钟更新）
- **lag_size=0**：使用最新数据，敏感度高，适合实时定价

### 拟合步骤

```
1. 加载分钟 K 数据（kline）→ resample 到完整 1 分钟序列
2. bfitter.breakeven()：对每个执行价求 delta-hedge 盈亏为零的 breakeven vol
3. jwfitter.fit()：L-BFGS-B 优化 JWSS7 参数，最小化 vega 加权残差
4. verifyVolSurface()：套利校验
5. 写入 ModelParams 表（type=VolMark-h-2021-01-02）
```

### 分钟 K 数据要求

- 每天需要 ≥ 1439 根 bar（`ts_builder` 过滤条件）
- 稀疏数据（只有成交的 bar）需 **resample + ffill** 补全，再用于拟合
- 美股需额外过滤**节假日跨天跳空 bar**（节假日前最后一根到节假日后第一根，跨度 48h+，会高估 realized vol）

---

## 4. 加密资产 vs 美股期权

| 维度 | 加密资产 | 美股（Pionex 5×24） |
|------|----------|-------------------|
| 交易时段 | 365.25 天 × 24h 连续 | 周一至周五全天，NYSE 节假日停盘 |
| 年化基准 | 31,557,600 秒 | 21,772,800 秒 |
| 节假日处理 | 无需处理 | 需过滤跨节假日 bar（NYSE 约9个/年） |
| 到期日规则 | 每月最后一个周五 | 每月**第三个周五**（遇节假日提前至周四） |
| 到期时间 | 16:00 CST | **16:00 ET**（含夏令时自动切换） |
| Skew 方向 | 通常正 skew 或平 | 通常负 skew（put 端更贵） |

**节假日日历**：使用 `pandas_market_calendars`（NYSE 日历），约9个节假日/年，含元旦、MLK日、总统日、耶稣受难日、阵亡将士纪念日、独立日、劳动节、感恩节、圣诞节。

---

## 5. 到期日规则

### 加密资产（月末最后周五）

```
季月（3/6/9/12月）+ 当前月 + 下两个月，各取最后一个周五
```

### 美股（第三个周五）

```
每月第三个周五，遇 NYSE 节假日提前一天到周四
```

### 三档到期日结构

| 档位 | 到期区间 | 步长倍数 | 触发条件 |
|------|---------|---------|---------|
| 短期（short） | T+1, T+2 交易日 | ×1 | 每次循环 |
| 中期（medium） | 未来3个周五 | ×2 | 每次循环 |
| 长期（long） | 未来3个月末/月第三周五 | ×3 | **每月第一个交易日**触发 |

---

## 6. 执行价网格设计

### Strike Band

执行价范围：**[现货 × 0.5, 现货 × 2.5]**（50%–250%）

用 z-score 边界转换到执行价：
```
total_vol = atmfvol × sqrt(TTM)
lb = max(-2.0, log(0.5) / total_vol)    ← 下边界 z
ub = min(+2.0, log(2.5) / total_vol)    ← 上边界 z
strike_range = spot × exp([lb, ub] × total_vol)
```

### Granularity（执行价步长）

- 按资产类型硬编码绝对步长（非百分比）
- 示例：BTC=500, ETH=50, SOL=4, SLVX=2
- 步长乘数：短期×1，中期×2，长期×3
- **美股步长参考**：$50–60 价位 → $1–2；>$200 → $5；$25–$200 → $2.5

---

## 7. Vol Surface 套利校验

通过 `verifyVolSurface()` 检查，**两项都通过才允许发布**：

### 无日历套利（Forward Variance Check）

```
每个执行价：forward variance = vol² × TTM
相邻 TTM 的 forward variance 必须单调递增
若 fwd_var[T2] - fwd_var[T1] ≤ 0 → 日历套利存在
```

### 无蝶式套利（Butterfly Convexity Check）

```
对每个 TTM 切片：C(K-a) + C(K+a) > 2×C(K)
即 call price 关于执行价必须凸
违反 → 可以构造无风险蝶式套利
```

---

## 8. 常见误区

| 误区 | 正确做法 |
|------|---------|
| 加密/美股用同一年化常数 | 加密 365.25×24h，Pionex 美股 252×24h，不能混用 |
| 稀疏 kline 直接喂给 bfitter | 先 resample+ffill 补全到完整 1 分钟序列 |
| 美股节假日跳空 bar 未过滤 | 检测相邻 bar 间隔是否跨越非交易日，跨越则清零该 return |
| 用 Strike 绝对值画 vol 曲面 | vol 曲面 X 轴应为 moneyness（K/S），与现价无关 |
| atmfvol 高就认为期权贵 | atmfvol 是波动率，还需结合 TTM 和执行价位置看权利金 |
| vol mark 参数直接拿加密参数用于美股 | 两类资产 skew 方向不同（美股通常为负 skew），参数不可复用 |
| lag_size=0 用于生产 | 生产环境用 lag_size=30，避免单日异常事件污染参数 |
| 长期合约每次都重新生成执行价 | 长期合约仅在月初第一个交易日生成，其余时间只更新 MidVol |
| 不校验套利就发布 vol surface | 必须通过 forward variance + butterfly convexity 两项检验 |
| 美股到期日用"月末最后周五" | 美股标准到期日是**第三个周五**，月末最后周五是加密的规则 |
