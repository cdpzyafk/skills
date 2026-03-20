# Claude Code 技能库

面向金融科技工程团队的 Claude Code 自定义技能集合，覆盖语言规范、领域专业、流程自动化三大方向。

---

## 安装

### 前提条件

安装 [Claude Code](https://claude.ai/code)，技能通过其 `Skill` 工具系统加载。

### 安装技能库

```bash
git clone <repo-url> ~/.claude/skills
```

技能目录放入 `~/.claude/skills/` 后，Claude Code 会自动发现并注册所有技能。

---

## 技能一览

### 语言技能

| 技能 | 触发场景 | 说明 |
|------|----------|------|
| `golang-pro` | 任何 Go 代码编写、审查、调试、重构 | Go 1.21+ 全生命周期规范，覆盖错误处理、并发、性能、调试，内置金融领域规则 |
| `python-pro` | Python 应用开发、FastAPI/Django/Flask、数据科学、CLI 工具 | Python 3.11+ 类型安全、async 模式、生产级代码规范 |

### 领域技能

| 技能 | 触发场景 | 说明 |
|------|----------|------|
| `fintech-product-manager` | 产品调研、竞品分析、PRD 编写、结构化产品、双币理财 | 金融财富管理产品研究与评估，覆盖监管可行性和风险评估 |
| `kb-creator` | 交易系统中涉及账户分片、精度计算、交易所特定逻辑时 | 维护 `.claude/knowledge/` 知识库，防止隐性假设破坏正确性 |

### 流程技能

| 技能 | 触发场景 | 说明 |
|------|----------|------|
| `jira-task` | 提及 Jira issue 编号（如 TRAD-83）、"实现这个票"、"根据 jira 任务" | 全自动流水线：拉取 → 分析代码 → 设计 → 实现 → 简化 → QA |
| `skill-creator` | 创建新技能、优化现有技能、运行技能评估 | 技能全生命周期管理，含性能基准测试和描述精度优化 |

### 质量技能

| 技能 | 触发场景 | 说明 |
|------|----------|------|
| `architect-reviewer` | 评估系统设计、架构模式、微服务边界、技术选型 | 架构决策评审，关注可扩展性、技术债和集成策略 |
| `qa-expert` | 需要 QA 策略、测试规划、缺陷管理、自动化框架设计时 | 全研发周期质量保障，覆盖质量指标分析和测试自动化 |
| `code-simplifier` | 代码变更后的清理与收尾 | 在保持功能不变的前提下提升代码可读性和一致性 |

---

## 技能目录结构

```
skills/
├── golang-pro/
│   ├── SKILL.md                  # 入口：核心规则 + 渐进式披露导航表
│   ├── README.md                 # 详细使用说明
│   └── references/               # 按需加载的深度参考文档
│       ├── foundation.md
│       ├── error-handling.md
│       ├── concurrency.md
│       ├── design-patterns.md
│       ├── testing-quality.md
│       ├── performance.md
│       └── debugging.md
├── python-pro/
│   └── SKILL.md
├── fintech-product-manager/
│   └── SKILL.md
├── kb-creator/
│   └── SKILL.md
├── jira-task/
│   └── SKILL.md
├── skill-creator/
│   └── SKILL.md
├── architect-reviewer/
│   └── SKILL.md
├── qa-expert/
│   └── SKILL.md
└── code-simplifier/
    └── SKILL.md
```

---

## jira-task 自动化流水线

`jira-task` 是本库的核心工作流技能，触发后全程无需人工干预：

```
1. 拉取 Jira issue（summary / description / AC / comments）
        ↓
2. 探索代码库，定位相关文件
        ↓
3. 设计变更方案，写入 doc/<ISSUE-KEY>.md
        ↓
4. fintech-product-manager 自动评审（功能完整性 + 代码覆盖度）
        ↓
5. golang-pro / python-pro 按设计实现变更
        ↓
6. code-simplifier 清理新增代码
        ↓
7. qa-expert QA 验收，输出报告
```

---

## 使用方式

### 自动触发

Claude Code 根据技能描述自动匹配触发，无需手动调用：

```
"帮我 review 这段 Go 代码"           → golang-pro
"看一下 TRAD-83"                     → jira-task
"做一份双币理财的竞品分析"            → fintech-product-manager
"这个微服务拆分方案合理吗"            → architect-reviewer
```

### 手动调用

```
/golang-pro
/jira-task TRAD-83
/qa-expert
```

---

## 技能开发

使用 `skill-creator` 技能创建或优化技能：

- 每个技能是一个独立目录，包含 `SKILL.md` 作为入口
- `SKILL.md` 头部 frontmatter 定义 `name` 和 `description`，description 决定自动触发准确率
- 复杂技能可通过 `references/` 目录实现渐进式披露，减少无关上下文消耗

```yaml
---
name: my-skill
description: 精确描述触发时机，Claude 依此自动匹配
---
```
