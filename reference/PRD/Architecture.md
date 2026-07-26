## 架构引用规则

- 应用架构只在项目级 Architecture.md文档中定义一次。
- `AGENTS.md`、PRD、SPEC、SOP 和其他关联文档，需要表述应用架构的，只能声明、引用应用架构原文，不得再定义、改写、摘抄或粘贴等。声明内容：本项目采用哪种应用架构，该架构的详细内容见project root/reference/PRD/Architecture.md。写代码前，必须读一遍架构原文。

## FCMA架构

FCMA（Feature-Centric Modular Architecture）按用户功能组织代码的一种模块化应用架构。

注意，Feature=用户功能，所以该架构不是按页面、文件类型或语音组织代码。这个架构的根本目的是尽可能地复用 core 和 shared（下面统称各种能力）。如果两个 feature 的底层能力是一样的，但 feature 前端名称不一样，那也应该复用能力，而不是重新造轮子。否则会造成代码冗余，还会造成业务逻辑的歧义与混乱。
前端页面通常不等于 Feature。一个页面可以组合多个 Feature；只有页面与一项用户能力完全一一对应时，页面才可以作为一个 Feature。

### 模块定义

- Feature：用户可以独立使用、描述和验收的一项完整能力。
- Core：不包含具体业务含义的系统能力。
- Shared：不包含业务逻辑的纯公共能力。
- App：框架要求的薄入口，只负责路由、协议转换和 Feature 组合，不承载业务逻辑。

### 模块落盘

每个 Feature、Core 或 Shared 模块必须使用独立文件夹：

```text
features/<feature-name>/
core/<capability-name>/
shared/<capability-name>/
```

模块所需的界面、逻辑、样式、类型、接口实现、测试和专属资源必须收拢在该模块文件夹内。

代码默认归属 Feature。只有确认属于系统能力时才能放入 Core；
只有确认无业务含义且可跨模块复用时才能放入 Shared。
不确定时保留在 Feature，禁止提前抽象。

模块必须使用 `index.ts` 作为对外入口。外部只使用模块公开入口，不得随意引用模块内部文件。

### 模块之间的依赖规则

允许：

```text
app -> features
app -> shared
features -> core
features -> shared
core -> shared
```

禁止：

```text
feature -> feature
core -> feature
shared -> core
shared -> feature
```

多个 Feature 由 App 组合，不得互相调用。

### Agent 写代码前声明

Agent 创建或修改代码前必须先输出：

```text
模块：features/<feature-name> | core/<capability-name> | shared/<capability-name>
职责：该模块独立负责什么
包含：本次放入模块的文件或代码
依赖：本模块需要调用哪些模块
归属理由：为什么不属于另外两层
```

示例：

```text
模块：features/subjective-rating
职责：提交和查看主观评分
包含：评分界面、评分规则、接口实现、样式和测试
依赖：core/database、shared/radar-types
归属理由：包含主观评分业务含义，因此不属于 Core 或 Shared
```

完成归属判断后才能按照<模块落盘>章节选择路径，创建或修改代码。

### 模块示例

```text
features/subjective-rating/
├── index.ts
├── SubjectiveRatingSection.tsx
├── ratingRules.ts
├── submitRating.ts
├── subjectiveRating.module.css
└── subjectiveRating.test.ts
```

上述文件共同完成“提交和查看主观评分”这一项用户能力。数据库连接属于 `core/database/`，无业务含义的公共类型属于 `shared/<module>/`。

### 禁止事项

- 禁止把页面容器直接当作 Feature，并在其中混入多项用户能力。
- 禁止把 Feature 业务规则放入 Core 或 Shared。
- 禁止在 `features/`、`core/`、`shared/` 根层散落模块实现文件。
- 禁止按 `controllers/`、`services/`、`utils/`、`models/` 作为项目主结构。
- 禁止创建混合多种职责的万能模块。
- 禁止为了降低文件行数创建没有独立职责的空壳模块。


## 项目初始化的最小目录树

AGENT根据Achietecture.md进行初始化目录，若选用FCMA架构，初始化都最小目录树如下：

```Markdown
project-root/
├── AGENTS.md
├── reference/                         # 代码生成前创建，整个研发生命周期持续维护
│   ├── PRD.md                         # 简单项目：单个 PRD 文档
│   ├── SOP.md                         # 简单项目：单个 SOP 文档
│   ├── PRD/                           # 复杂项目：替代 PRD.md
│   │   ├── PRD.md                     # 主文档，声明并索引各子文档
│   │   └── <prd-topic>.md             # 按业务主题拆分的子文档
│   ├── SOP/                           # 复杂项目：替代 SOP.md
│   │   ├── SOP.md                     # 主文档，声明并索引各子文档
│   │   └── <sop-topic>.md             # 按流程主题拆分的子文档
│   ├── brief.md
│   ├── design.md
│   ├── SPEC.md
│   ├── requirements.md                # 项目依赖清单，记录要求的硬件、软件等
│   └── <other-reference>              # 其他参考文献
├── app/
├── features/
│   └── <feature-name>/
├── core/
│   └── <capability-name>/
├── shared/
│   └── <capability-name>/
├── docs/                              # 用户文档
├── knowledge/                         # 技术文档
└── env/
```
