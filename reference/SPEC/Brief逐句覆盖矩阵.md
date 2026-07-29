# Brief 逐句覆盖矩阵

## 1. 覆盖规则

本矩阵只证明 [`brief.md`](../brief.md) 中每个语义单元在 SPEC 中有落点，不重新定义需求。
当前绑定的 Brief 文件 SHA-256 为
`d8443fd40d094445cead2dda3cce8d6f0c99677269893836ddf891f876dcb19f`。

定位符规则：

- `Lx-Sy`：第 x 行的第 y 个正文句子；
- `Lx-Ly-Sz`：跨行正文句子；
- `Lx-Iy`：第 x 行开始的编号项；
- `Lx-B`：第 x 行的列表项；
- `Lx-M`：第 x 行的图片或视觉参考；
- `Lx-H`：承担需求含义的引导语。

标题只组织结构，不单独形成需求。正文、编号项、列表项、平台项、参考图和不完整但仍表达约束
的原句全部进入下表。

## 2. 文档说明、目标与 MVP

| Brief 单元 | SPEC 落点 |
| --- | --- |
| `BF-001` / `L3-S1` | `SPEC-DOC-001` |
| `BF-002` / `L5-S1` | `SPEC-DOC-002` |
| `BF-003` / `L5-S2` | `SPEC-DOC-002`、`SPEC-ACCEPT-001` |
| `BF-004` / `L9-S1` | `SPEC-PRODUCT-001` |
| `BF-005` / `L11-S1` | `SPEC-PRODUCT-002` |
| `BF-006` / `L11-S2` | `SPEC-PRODUCT-005`、`SPEC-DASHBOARD-028` |
| `BF-007` / `L13-S1` | `SPEC-PRODUCT-003`、`SPEC-PRODUCT-006` |
| `BF-008` / `L13-S2` | `SPEC-PRODUCT-003`、`SPEC-PRODUCT-006` |
| `BF-009` / `L15-S1` | `SPEC-PRODUCT-004`、`SPEC-FLASH-001` |
| `BF-010` / `L19-H` | `SPEC-MVP-001` 至 `SPEC-MVP-009` |
| `BF-011` / `L21-I1` | `SPEC-MVP-001`、`SPEC-MVP-002` |
| `BF-012` / `L22-I2` | `SPEC-MVP-004`、`SPEC-FIRMWARE-006` |
| `BF-013` / `L23-L24-S1` | `SPEC-MVP-003`、`SPEC-FIRMWARE-004`、`SPEC-FIRMWARE-005` |
| `BF-014` / `L25-I3` | `SPEC-MVP-005`、`SPEC-FLASH-007` |
| `BF-015` / `L26-S1` | `SPEC-MVP-006` |
| `BF-016` / `L26-S2` | `SPEC-MVP-002`、`SPEC-GOV-005`、`SPEC-GOV-006` |
| `BF-017` / `L27-I5` | `SPEC-MVP-007`、`SPEC-PRODUCT-004` |
| `BF-018` / `L28-I6` | `SPEC-MVP-008`、`SPEC-FLASH-002`、`SPEC-FLASH-008` |
| `BF-019` / `L30-S1` | `SPEC-MVP-004`、`SPEC-FIRMWARE-006` |

## 3. 一级页面开关

| Brief 单元 | SPEC 落点 |
| --- | --- |
| `BF-020` / `L36-L37-S1` | `SPEC-PAGE-001` 至 `SPEC-PAGE-004` |

## 4. AGENTS 看板总体要求

| Brief 单元 | SPEC 落点 |
| --- | --- |
| `BF-021` / `L41-S1` | `SPEC-DASHBOARD-001` |
| `BF-022` / `L43-S1` | `SPEC-DASHBOARD-002`、`SPEC-DASHBOARD-003` |
| `BF-023` / `L43-S2` | `SPEC-DASHBOARD-004` |
| `BF-024` / `L45-S1` | `SPEC-DASHBOARD-005` |
| `BF-025` / `L47-H` | `SPEC-DASHBOARD-006` |
| `BF-026` / `L49-B` | `SPEC-DASHBOARD-006` |
| `BF-027` / `L50-B` | `SPEC-DASHBOARD-006` |
| `BF-028` / `L51-B` | `SPEC-DASHBOARD-006` |
| `BF-029` / `L52-B` | `SPEC-DASHBOARD-006` |
| `BF-030` / `L54-S1` | `SPEC-DASHBOARD-007` |
| `BF-031` / `L54-S2` | `SPEC-DASHBOARD-008` |
| `BF-032` / `L56-S1` | `SPEC-DASHBOARD-010` |
| `BF-033` / `L56-S2` | `SPEC-DASHBOARD-011` |
| `BF-034` / `L56-S3` | `SPEC-DASHBOARD-012` |
| `BF-035` / `L58-S1` | `SPEC-DASHBOARD-013`、`SPEC-DASHBOARD-014` |
| `BF-036` / `L58-S2` | `SPEC-DASHBOARD-013`、`SPEC-DASHBOARD-027` |
| `BF-037` / `L60-L61-S1` | `SPEC-DASHBOARD-015` 至 `SPEC-DASHBOARD-017` |
| `BF-038` / `L63-L64-S1` | `SPEC-DASHBOARD-018`、`SPEC-DASHBOARD-014` |

## 5. 概览与详情字段

| Brief 单元 | SPEC 落点 |
| --- | --- |
| `BF-039` / `L68-H` | `SPEC-DASHBOARD-019` |
| `BF-040` / `L70-B` | `SPEC-DASHBOARD-019` |
| `BF-041` / `L71-B` | `SPEC-DASHBOARD-019` |
| `BF-042` / `L72-B` | `SPEC-DASHBOARD-019` |
| `BF-043` / `L74-S1` | `SPEC-DASHBOARD-020` |
| `BF-044` / `L74-S2` | `SPEC-DASHBOARD-020` |
| `BF-045` / `L78-H` | `SPEC-DASHBOARD-002`、`SPEC-DASHBOARD-021` 至 `SPEC-DASHBOARD-023` |
| `BF-046` / `L80-I1` | `SPEC-DASHBOARD-021` |
| `BF-047` / `L81-B` | `SPEC-DASHBOARD-021` 第 1 项 |
| `BF-048` / `L82-B` | `SPEC-DASHBOARD-021` 第 2 项 |
| `BF-049` / `L83-B` | `SPEC-DASHBOARD-021` 第 3 项 |
| `BF-050` / `L84-B` | `SPEC-DASHBOARD-021` 第 4 项 |
| `BF-051` / `L85-I2` | `SPEC-DASHBOARD-022` |
| `BF-052` / `L86-B` | `SPEC-DASHBOARD-022` 第 1 项 |
| `BF-053` / `L87-B` | `SPEC-DASHBOARD-022` 第 2 项 |
| `BF-054` / `L88-B` | `SPEC-DASHBOARD-022` 第 3 项 |
| `BF-055` / `L89-B` | `SPEC-DASHBOARD-022` 第 4 项 |
| `BF-056` / `L90-I3` | `SPEC-DASHBOARD-023` |
| `BF-057` / `L91-B` | `SPEC-DASHBOARD-023` 第 1 项 |
| `BF-058` / `L92-B` | `SPEC-DASHBOARD-023` 第 2 项 |
| `BF-059` / `L93-B` | `SPEC-DASHBOARD-023` 第 3 项 |
| `BF-060` / `L94-B` | `SPEC-DASHBOARD-023` 第 4 项 |
| `BF-061` / `L95-B` | `SPEC-DASHBOARD-024` |
| `BF-062` / `L96-B` | `SPEC-DASHBOARD-025` |

## 6. 视觉参考、数据来源与缺失字段

| Brief 单元 | SPEC 落点 |
| --- | --- |
| `BF-063` / `L98-H` | `SPEC-DASHBOARD-014` |
| `BF-064` / `L100-L102-M` | `SPEC-DASHBOARD-014`、`SPEC-DASHBOARD-019`、`SPEC-DASHBOARD-021` |
| `BF-065` / `L104-L105-M` | `SPEC-DASHBOARD-014`、`SPEC-DASHBOARD-021` |
| `BF-066` / `L107-L108-M` | `SPEC-DASHBOARD-014`、`SPEC-DASHBOARD-022` |
| `BF-067` / `L110-L111-M` | `SPEC-DASHBOARD-014`、`SPEC-DASHBOARD-023` |
| `BF-068` / `L113-S1` | `SPEC-DASHBOARD-026`、`SPEC-GOV-003` |
| `BF-069` / `L113-S2` | `SPEC-DASHBOARD-009` |

## 7. AGENTS 看板物理旋钮

| Brief 单元 | SPEC 落点 |
| --- | --- |
| `BF-070` / `L117-S1` | `SPEC-DASHBOARD-029`、`SPEC-DASHBOARD-033` |
| `BF-071` / `L117-S2` | `SPEC-DASHBOARD-029` |
| `BF-072` / `L119-B` | `SPEC-DASHBOARD-030` |
| `BF-073` / `L120-B` | `SPEC-DASHBOARD-030` |
| `BF-074` / `L121-B` | `SPEC-DASHBOARD-031` |
| `BF-075` / `L122-B` | `SPEC-DASHBOARD-032` |

## 8. 系统设置一级列表旋钮

| Brief 单元 | SPEC 落点 |
| --- | --- |
| `BF-076` / `L126-S1` | `SPEC-ROTARY-001` |
| `BF-077` / `L126-S2` | `SPEC-ROTARY-002` 至 `SPEC-ROTARY-004` |
| `BF-078` / `L128-B` | `SPEC-ROTARY-002`、`SPEC-ROTARY-004` |
| `BF-079` / `L129-B` | `SPEC-ROTARY-003`、`SPEC-ROTARY-004` |

## 9. 研发约束

| Brief 单元 | SPEC 落点 |
| --- | --- |
| `BF-080` / `L133-S1` | `SPEC-GOV-001` |
| `BF-081` / `L135-S1` | `SPEC-GOV-002` |
| `BF-082` / `L137-S1` | `SPEC-GOV-002` |
| `BF-083` / `L137-S2` | `SPEC-GOV-002`、`SPEC-GOV-004` |
| `BF-084` / `L139-S1` | `SPEC-GOV-003` |
| `BF-085` / `L141-L142-S1` | `SPEC-GOV-004` |
| `BF-086` / `L142-S2` | `SPEC-GOV-004` |
| `BF-087` / `L142-S3` | `SPEC-GOV-002`、`SPEC-GOV-004` |
| `BF-088` / `L144-L145-S1` | `SPEC-GOV-005` |
| `BF-089` / `L146-S1` | `SPEC-GOV-005`、`SPEC-GOV-006` |
| `BF-090` / `L146-S2` | `SPEC-DOC-002`、`SPEC-GOV-008` |
| `BF-091` / `L146-L147-S3` | `SPEC-GOV-007` |

## 10. 覆盖结论

- Brief 语义单元：91；
- 已映射单元：91；
- 未映射单元：0；
- 每个单元至少对应一个稳定 SPEC 条款；
- Brief 标题不形成独立需求，图片参考已经作为媒体单元纳入；
- Brief 第 144 至 147 行虽存在不完整表达，仍按其可确定部分分别落入 `SPEC-GOV-005` 至
  `SPEC-GOV-008`，没有补造新的产品功能。
