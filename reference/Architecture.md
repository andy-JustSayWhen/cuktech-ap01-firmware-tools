## 本文怎样使用

- 项目的代码组织规则只在 `reference/Architecture.md` 中定义。
- 其他文档只说明本项目采用哪种架构，并链接到本文；不得复制或改写本文的定义。写代码前必须先读本文。

## FCMA 架构

FCMA（Feature-Centric Modular Architecture，按用户功能分组组织代码的方式）是本项目的代码组织架构。

代码按用户能独立使用和验收的功能分组，不按页面或文件类型分组。两个用户功能需要同一项底层能力时，必须共用同一份实现，避免重复代码和不一致的业务规则。一个页面可以包含多个 Feature（用户功能）。只有当整个页面恰好只实现一项用户功能时，才可以把该页面作为一个 Feature。

### 模块定义

- Feature（用户功能模块）：用户可以独立使用、描述和验收的一项完整能力。
- Core（底层能力模块）：不包含具体业务含义的系统能力。
- Shared（公共模块）：不包含业务逻辑的通用能力。
- App（程序入口模块）：只负责转发请求、转换通信格式和组合 Feature，不包含具体业务规则。

### 模块文件放在哪里

每个 Feature、Core 或 Shared 模块必须使用独立文件夹：

```text
features/<feature-name>/
core/<capability-name>/
shared/<capability-name>/
```

模块所需的界面、逻辑、样式、类型、接口实现、测试和专属资源必须放在该模块文件夹内。

代码默认归属 Feature。只有确认属于系统能力时才能放入 Core；只有确认无业务含义且可跨模块复用时才能放入 Shared。不确定时先保留在 Feature，不要在还没有共用需求时就拆出 Core 或 Shared。

模块必须使用约定的入口文件作为对外入口。外部只使用模块公开入口，不得随意引用模块内部文件。

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

完成归属判断后，再按“模块文件放在哪里”一节选择路径，然后创建或修改代码。

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

Agent 根据 `Architecture.md` 创建项目目录。选用 FCMA 架构时，最小目录结构如下：

```Markdown
project-root/
├── AGENTS.md
├── reference/                         # 代码生成前创建，整个研发生命周期持续维护
│   ├── PRD/                           # 非必须
│   │   ├── PRD.md                     # 主文档，声明并索引各子文档
│   │   └── <prd-topic>.md             # 若干个子文档
│   ├── SOP/                           # 非必须
│   │   ├── SOP.md                     # 主文档，声明并索引各子文档
│   │   └── <sop-topic>.md             # 若干个子文档
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
└── knowledge/                         # 技术文档
```
