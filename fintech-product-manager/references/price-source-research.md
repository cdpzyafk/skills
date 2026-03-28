# 价格源调研专项方法论

## 调研框架模板

对每个数据源，必须覆盖以下 10 个维度（所有数据必须实测，不可凭记忆填充）：

```
1. 资产覆盖：支持哪些资产类别（加密/美股/期权/期货/FX/商品）
2. 费用结构：免费层 vs 付费层，具体价格（实测确认，精确到月/年档位）
3. 数据时段：7×24 / 交易日 / 盘前盘后覆盖情况（区分交易日/盘前/盘后/周末/节假日）
4. 数据来源与可信度：原始数据来自哪里（SIP/交易所直连/Oracle 聚合）
5. 延迟与稳定性：API 响应延迟、Uptime SLA、WebSocket 推送频率
6. 闪崩/停牌保护：平台内置机制
7. 认证方式：API Key / RSA 私钥 / 无需认证
8. SDK 生态：支持语言、链上集成能力
9. 历史数据深度
10. 速率限制与订阅限制
```

**数据获取优先级（第一性原则）：**

```
优先级 1 → curl 直接调用 API
优先级 2 → 静态 JS bundle 正则提取（适用动态渲染的定价页）
优先级 3 → Playwright 截图 + 视觉分析
优先级 4 → 官方文档 WebFetch（补充验证，不作为唯一来源）
```

---

## curl 失败 → Playwright 自动降级流程

```
Step 1: 执行 curl GET <url>
  ↓ 成功（HTTP 200，非空响应）
  → 检查是否含 __NEXT_DATA__ / _next/static / ReactDOM / <div id="root">
    → 否：直接解析 JSON 或提取文本
    → 是（动态渲染）：
        尝试从 JS bundle 用正则提取嵌入数据
        grep -oP '"price":\K[0-9.]+' / '"amount":\K[0-9]+'
        → 成功：使用提取数据，标注为"从 JS bundle 提取"
        → 失败：进入 Step 3

  ↓ 失败（HTTP 403/429/5xx / 超时 / 空响应）
Step 2: 尝试更换 User-Agent 重试一次
  curl -H "User-Agent: Mozilla/5.0 ..." <url>
  → 成功：继续
  → 失败：进入 Step 3

Step 3: 执行 scripts/fetch_price_source.sh <url> --screenshot-out /tmp/screenshot.png
  → 截图保存成功（exit code 2）：
      使用 Read 工具读取截图进行视觉分析
      同时读取脚本输出的"页面可见文本摘要"
  → 失败（exit code 1）：
      在报告中标注"无法自动获取，需人工访问"
      记录 URL 和尝试时间
      如能访问 Wayback Machine，尝试存档页面
```

发现域名/URL 无效时，先尝试 `[brand].com` / `docs.[brand].com` / `api.[brand].com`，再确认正确地址。

---

## 输出格式

```
- 100 字执行摘要
- 核心对比表（所有源并列）
- 各源详细分析（300-500 字/源）
- 场景选型建议（DeFi / 量化 / 盘中定价 / 低频研究）
- 风险提示表
- API 速查代码块
- 原始调研数据来源索引（URL + 抓取时间）
```

---

## 规则约束

```
□ 不可凭记忆填充，每条数据必须有对应 API 调用或页面抓取记录
□ 动态页面不可仅依赖 curl，必须触发 JS bundle 提取或 Playwright 降级
□ 费用数据精确到月/年档位，标注付费方式（月付 vs 年付折合月价）
□ 时段覆盖必须区分交易日/盘前/盘后/周末/节假日
□ 若某源需要 API Key 才能获取实时数据，明确标注并说明如何申请
```

已知数据源的历史档案、防坑记录和 API 速查，参见 `references/price-source-kb.md`。
