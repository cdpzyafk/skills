---
name: update-monitor-logic
description: >
  根据监控代码逻辑更新对应文档,并将文档同步到Confluence.
  Triggers on: "更新监控文档", "监控逻辑有变动", "同步监控文档", "更新告警文档",
  "整理监控逻辑", "帮我更新一下监控描述", "监控改了要更新文档".
---

# update-monitor-logic

为 `docs/` 中的监控文档提供**新建**、**同步更新**、**批量发布到 Confluence** 三种工作流。

---

## 文档存放路径

**实际路径**：`docs/<name>-monitor-doc.md`（注意：不是 `docs/monitor/`）

每个监控文档的**开头注释**格式取决于创建方式：

- **已发布到 Confluence 的文档**：只需第一行 `<!-- Confluence: <url> -->`
- **用本 skill 模板新建的文档**：包含完整 4 行 metadata（见工作流 A）

---

## 判断工作流

| 情景 | 走哪条路 |
|------|---------|
| 用户指定文档不存在，或要"从源码整理/创建"文档 | **工作流 A：新建** |
| 文档已存在，源码有变动，需同步差异 | **工作流 B：更新** |
| 文档已存在（含或不含 Confluence URL），需批量发布到 Confluence 父页面下 | **工作流 C：批量发布** |

---

## 工作流 A：新建文档

### 步骤 A1：读取源码

读取监控包下所有 `.go` 文件。告警消息结构体可能在两个位置，都需要检查：

| 位置 | 说明 |
|---|---|
| `core/<package>/msg*.go` | 结构体定义在包内（优先检查） |
| `alert/*.go` | 通用告警结构体（若包内没有） |

重点提取：

| 文件 | 提取内容 |
|---|---|
| `export.go` | Init timer 间隔（首次 + 后续）、`AlertGroup` 参数 |
| `check*.go` | 核心检测逻辑、跳过条件、触发条件、阈值 |
| `pacers.go`（如有） | TriggerWindow、Pacer 间隔 |
| `threshold.go`（如有） | 默认阈值、特殊币对阈值 |
| `msg*.go` / `alert/*.go` | DedupKey、ServiceName、Summary 模板、Detail() 格式 |

**AlertGroup 语义**：若 `export.go` 中有 `alert.NewAlertGroup(wc, wi, pi)`，需读取 `alert/alert_group.go` 确认三个参数的含义（TriggerWindow count、window 时长、Pacer 间隔）。

整理出：
- 执行频率（首次延迟 + 循环间隔）
- 触发范围（遍历哪些币对，跳过哪些条件）
- 检测逻辑与阈值（含注释掉的逻辑，注明"已注释/未启用"）
- 告警去重配置（TriggerWindow count、window、Pacer 间隔）
- PagerDuty 字段（DedupKey、ServiceName、Summary、Severity）
- Detail() 输出格式（逐行记录）
- Bypass 条件（dev 环境是否抑制）

### 步骤 A2：写文档

按以下模板创建 `docs/<name>-monitor-doc.md`。若用户已提供 Confluence URL，直接填入；若未提供则留空。

```markdown
<!-- Space: vaOwEmByt8y2 -->
<!-- Parent: <从现有文档推断，或留空> -->
<!-- Title: 监控逻辑：<中文名> -->
<!-- Confluence: <用户提供的 URL，或留空> -->

# 监控逻辑：<中文名>（<package>）

**包路径：** `core/<package>`

## 背景

<该监控的业务意义，一两句话>

---

## 执行频率

| 阶段 | 间隔 |
|---|---|
| 初次执行 | 启动后 X 秒 |
| 后续执行 | 每 X 秒 |

---

## 触发范围

遍历所有 active 币对，跳过以下情况：
- ...

---

## 检测逻辑

### 告警阈值
...

### 触发条件
...

---

## 检查逻辑（伪代码）

​```
...
​```

---

## 告警机制

### 去重与限流

| 参数 | 值 |
|---|---|
| TriggerWindow | X 分钟内累计触发 X 次后发送 |
| Pacer | 每币对每 X 分钟最多发送一次 |

### PagerDuty 告警字段

| 字段 | 值 |
|---|---|
| `ServiceName` | `...` |
| `DedupKey` | `...:{ symbol}` |
| `Summary` | `{symbol} ...` |
| `Severity` | `critical` |
| `Bypass` | dev 环境为 `true` |

### 告警详情

​```
...
​```

---

## 数据来源

| 数据 | 来源 | 刷新频率 |
|---|---|---|
| ... | ... | ... |

---

## 关键代码位置

| 逻辑 | 文件 |
|---|---|
| 初始化与主循环 | `core/<package>/export.go` |
| 检查逻辑 | `core/<package>/check*.go` |
| 告警消息结构体 | `core/<package>/msg*.go` 或 `alert/...` |
```

若同一个包有**多个检查子流程**（如 USDT 保证金 vs 非 USDT 保证金），为每个子流程单独列一节。

### 步骤 A3：发布到 Confluence

若文档头部有 `<!-- Confluence: <url> -->`，直接更新（见下方"更新已有页面"）。

若没有 Confluence URL，需先**创建新页面**：

1. 从 `<!-- Title: ... -->` 或文档 H1 标题提取页面标题
2. 调用 `confluence_create_page`：
   - `space_key`: 从 URL 中取（如 `vaOwEmByt8y2`）
   - `title`: 页面标题
   - `parent_id`: 父页面 ID（用户提供）
   - `content`: 正文（**去掉**所有 `<!-- ... -->` 注释行）
   - `content_format`: "markdown"
3. 从返回结果取 `page_id`，拼成完整 URL 写回本地文件第一行：
   ```
   <!-- Confluence: https://pionex.atlassian.net/wiki/spaces/.../pages/<PAGE_ID> -->
   ```

**更新已有页面**（有 Confluence URL 时）：

1. 从 URL 末尾提取 PAGE_ID
2. 调用 `confluence_update_page`：
   - `page_id`: PAGE_ID
   - `title`: 文档标题
   - `content`: 正文（去掉所有注释行）
   - `content_format`: "markdown"
   - `version_comment`: 一句话说明（中文）

**标题重复冲突处理**：若 `create_page` 报 `A page already exists with the same TITLE`，用 `confluence_search` 搜索该标题找到已有页面 ID，直接复用其 URL 写入本地文件（不重复创建），并在汇报中注明"(已存在旧页面，未重新创建)"。

---

## 工作流 B：更新现有文档

### 步骤 B1：读取源码（同 A1）

### 步骤 B2：对比现有文档

逐节对比，列出差异点，例如：
- 执行间隔从 3s 变成了 5s
- 新增跳过条件
- TriggerWindow count 从 5 改成了 3
- 阈值变化
- DedupKey 格式变化

**如果没有差异**：报告"文档与代码一致，无需更新"，停止。

### 步骤 B3：更新文档

只修改有变动的章节：
- 文件开头的注释块完整保留（不论是 1 行还是 4 行格式）
- 未变动章节原样保留
- 语言和格式风格与原文一致

### 步骤 B4：同步到 Confluence（同 A3）

---

## 工作流 C：批量发布到 Confluence

用户希望将一批已有的本地文档批量发布（或补发）到 Confluence 某个父页面下。

### 步骤 C1：确认范围

1. 列出目标目录（通常是 `docs/`）下所有 `*-monitor-doc.md` 文件
2. 分类：
   - **已有 Confluence URL**（文件第一行有 `<!-- Confluence: ... -->`）→ 跳过（除非用户要求强制更新）
   - **无 Confluence URL** → 需要创建新页面

### 步骤 C2：提取标题

从每个文件提取页面标题，优先级：
1. 文件中的 `<!-- Title: ... -->` 注释（如有）
2. 文件第一个 `# ...` H1 标题

### 步骤 C3：批量创建页面

对每个"无 Confluence URL"的文件：

1. 调用 `confluence_create_page`：
   - `space_key`: 父页面所属 space key
   - `title`: 提取的标题
   - `parent_id`: 用户指定的父页面 ID
   - `content`: 文件正文（去掉所有 `<!-- ... -->` 注释行）
   - `content_format`: "markdown"
2. 将返回的 `page_id` 拼成 URL，**写入本地文件顶部**（第一行）：
   ```
   <!-- Confluence: https://pionex.atlassian.net/wiki/spaces/.../pages/<PAGE_ID> -->
   ```

**并行化**：多个文件的 Confluence 创建操作可以并行执行，以提升速度。

**标题冲突处理**：同 A3——搜索已有页面，复用其 URL，注明来源。

**本地文件不存在**：若 git 记录或上下文中有该文件内容但磁盘上缺失，先用 Write 工具重建文件，再执行发布步骤。

### 步骤 C4：汇报结果

| 状态 | 说明 |
|------|------|
| ✓ 已创建 | 新建页面并写回 URL |
| ✓ 已存在旧页面 | 找到重名页面，复用 URL |
| ⏭ 已跳过 | 文件已有 Confluence URL |
| ✗ 失败 | 记录错误原因 |

---

## 批量检查文档是否与代码同步

用户要求检查所有监控文档时：

1. 遍历 `docs/` 下所有 `*-monitor-doc.md` 文件
2. 从每个文档提取 `包路径`，找到对应源码目录
3. 对每个文档执行工作流 B
4. 最终输出汇总表：哪些有更新、哪些一致、哪些找不到源码

---

## 汇报格式

```
✓ 已创建/更新 docs/<file>.md
  变动：<简述>
✓ 已同步到 Confluence: <url>
```

若无 Confluence URL：

```
✓ 已创建/更新 docs/<file>.md
  变动：<简述>
⚠ 该文档尚未绑定 Confluence 页面，跳过同步
```

---

## 注意事项

- 只更新**与代码直接对应的客观事实**（间隔、阈值、字段值等），不要修改背景说明、语义解释等主观描述
- 注释掉的逻辑（如被注释的 Slack 告警）应在文档中注明"已注释/未启用"，不要完全忽略
- 保持伪代码章节的逻辑与源码一致，但风格不必完全照抄源码
- 若源码逻辑改动但文档描述依然正确（只是表述不同），不要改动文档
- `confluence_create_page` 返回的 `page_id` 字段名以实际 API 响应为准（可能是 `id` 或 `page_id`）
