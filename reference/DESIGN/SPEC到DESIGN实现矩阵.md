# SPEC 到 DESIGN 实现矩阵

## 1. 使用边界

本矩阵只索引 [`SPEC.md`](../SPEC.md) 全部稳定条款的设计、代码、验证和状态落点，不重新定义
需求、架构、技术术语或验收结论。设计纠偏流程只见 [`design.md`](../design.md) 第 2 节。

状态取 2026-07-30 当前仓库和已有证据。范围内只要有一条尚未通过，整行就不得视为完成。

## 2. 文档、产品与版本

| SPEC 条款 | DESIGN 落点 | 代码或维护落点 | 验证方法 | 当前状态 |
| --- | --- | --- | --- | --- |
| `SPEC-DOC-001` 至 `SPEC-DOC-004` | [`design.md`](../design.md) 第 1、3 节；[`项目交付与 WebUI 刷机工具 DESIGN`](项目交付与WebUI刷机工具.md) 第 2 节 | 后续文档核对任务 | Brief 指纹、91 个语义单元、SPEC 条款集合和引用完整性核对 | 拟定；Brief 到 SPEC 已有静态覆盖结果，自动任务未实现 |
| `SPEC-PRODUCT-001` 至 `SPEC-PRODUCT-006` | [`项目交付与 WebUI 刷机工具 DESIGN`](项目交付与WebUI刷机工具.md) 第 3、4、9 节 | `features/web_firmware_flash/`、`app/ap01_web.py`、发布包目录 | macOS 与 Windows 使用同一套 Chrome 流程；发布包敏感内容检查 | 拟定 |
| `SPEC-VERSION-001` 至 `SPEC-VERSION-003` | [`design.md`](../design.md) 第 2、3 节；[`项目交付与 WebUI 刷机工具 DESIGN`](项目交付与WebUI刷机工具.md) 第 2 节 | 后续文档核对任务 | 分别模拟 Brief、事实、依赖、操作和视觉变化，核对更新顺序 | 拟定 |

## 3. MVP、固件身份与刷机

| SPEC 条款 | DESIGN 落点 | 代码或维护落点 | 验证方法 | 当前状态 |
| --- | --- | --- | --- | --- |
| `SPEC-MVP-001` 至 `SPEC-MVP-003` | [`优化固件 DESIGN`](AP01-1.0.2_0031-opt.bin.md) 第 0、4、11、14 节；[`项目交付与 WebUI 刷机工具 DESIGN`](项目交付与WebUI刷机工具.md) 第 10 节 | `core/firmware_image/`、`features/offline_firmware_build/`、`features/settings_menu_wrap/` | 只读工作副本、官方基线检查、阶段成品确定性构建、修改范围和真机功能验收 | 部分已验证；跟踪材料已存在，当前只读工作副本能力拟定 |
| `SPEC-MVP-004` 至 `SPEC-MVP-006` | [`优化固件 DESIGN`](AP01-1.0.2_0031-opt.bin.md) 第 4、11、14 节；[`项目交付与 WebUI 刷机工具 DESIGN`](项目交付与WebUI刷机工具.md) 第 10 节 | `features/optimized_firmware_build/`、各固件功能模块、SOP 与案例 | 完整成品构建、唯一目标设备真实刷机、原厂能力回归和文档回写 | 阻塞 |
| `SPEC-MVP-007` 至 `SPEC-MVP-009` | [`项目交付与 WebUI 刷机工具 DESIGN`](项目交付与WebUI刷机工具.md) 第 3 至 10 节 | `features/web_firmware_flash/`、`app/ap01_web.py`、双平台发布包 | 零基础用户双平台完整操作、三组固件功能和发布总门禁 | 拟定 |
| `SPEC-FIRMWARE-001` 至 `SPEC-FIRMWARE-003` | [`优化固件 DESIGN`](AP01-1.0.2_0031-opt.bin.md) 第 0、2、4、14 节 | `core/firmware_image/`、`features/optimized_firmware_build/` | 版本化来源到只读工作副本、型号、版本、长度、完整文件指纹和三种文件身份检查 | 身份检查已实现；当前测试被可写来源门禁截停，只读副本能力拟定 |
| `SPEC-FIRMWARE-004` 至 `SPEC-FIRMWARE-005` | [`优化固件 DESIGN`](AP01-1.0.2_0031-opt.bin.md) 第 0、4.1、6.2、11、14 节 | `features/settings_menu_wrap/`、`core/rotary_encoder/` | 四个批准修改区间、文件尾记录、旋钮首尾与抖动真机验收 | 已验证的历史阶段成品；当前提交重建待只读副本能力完成 |
| `SPEC-FIRMWARE-006` 至 `SPEC-FIRMWARE-008` | [`优化固件 DESIGN`](AP01-1.0.2_0031-opt.bin.md) 第 4、10、11 节 | 完整固件构建组合、构建清单和冻结产物 | 确定性重建、修改区间外逐字节一致、禁止区无差异、完整指纹 | 阻塞 |
| `SPEC-FLASH-001` 至 `SPEC-FLASH-004` | [`项目交付与 WebUI 刷机工具 DESIGN`](项目交付与WebUI刷机工具.md) 第 4 至 6 节 | `features/web_firmware_flash/` 的页面、准备检查、设备识别和固件核对 | 双平台 Chrome 页面、敏感字段过滤、三种固件身份和门禁展示 | 拟定 |
| `SPEC-FLASH-005` 至 `SPEC-FLASH-008` | [`项目交付与 WebUI 刷机工具 DESIGN`](项目交付与WebUI刷机工具.md) 第 6 至 9 节 | `features/web_firmware_flash/` 的操作记录、上传下发适配和结果页 | 六类执行状态、断网与重入、重启上线、功能验收、发布包隔离 | 拟定 |

## 4. 一级页面开关

| SPEC 条款 | DESIGN 落点 | 代码或维护落点 | 验证方法 | 当前状态 |
| --- | --- | --- | --- | --- |
| `SPEC-PAGE-001` 至 `SPEC-PAGE-004` | [`优化固件 DESIGN`](AP01-1.0.2_0031-opt.bin.md) 第 5、14 节 | `features/primary_page_settings/`、`features/primary_page_navigation/` | 菜单进入、七项循环、复选操作、原厂对象和页面行为回归 | 验证中；历史组合方案已否定 |
| `SPEC-PAGE-005` 至 `SPEC-PAGE-007` | [`优化固件 DESIGN`](AP01-1.0.2_0031-opt.bin.md) 第 5、6、10.14、11、14 节 | `features/primary_page_settings/` 的保存与恢复代码、原厂实际切页调用局部挂接 | 逐回调方向与调用链审计、即时生效、保存失败、断电、重启、默认值和关闭当前页 | `FW-INTEGRATION-002` 已冻结但旋钮审计失效；完成 DESIGN 与代码纠偏前不可安装 |

## 5. AGENTS 看板

| SPEC 条款 | DESIGN 落点 | 代码或维护落点 | 验证方法 | 当前状态 |
| --- | --- | --- | --- | --- |
| `SPEC-DASHBOARD-001` 至 `SPEC-DASHBOARD-005` | [`优化固件 DESIGN`](AP01-1.0.2_0031-opt.bin.md) 第 7 至 10 节 | `features/agents_dashboard_firmware/`、`features/agents_dashboard/` | 四页完整包、五分钟刷新、格式选择、断网和最后成功结果 | 自动实现已存在；完整真机验收未通过 |
| `SPEC-DASHBOARD-006` 至 `SPEC-DASHBOARD-009` | [`优化固件 DESIGN`](AP01-1.0.2_0031-opt.bin.md) 第 7.4、8、9 节 | `features/agents_dashboard/bridge.py`、跨平台常驻包装、设备端顺序请求 | 四类主机、系统重启、顺序切换、字段级缺失 | macOS 已有部分运行证据；其余平台和设备端切换待验证 |
| `SPEC-DASHBOARD-010` 至 `SPEC-DASHBOARD-014` | [`优化固件 DESIGN`](AP01-1.0.2_0031-opt.bin.md) 第 0、7.2、7.5、7.6 节 | `reference/image/DESIGN/AP01-AGENTS看板/`、`features/agents_dashboard/renderer.py`、`features/agents_dashboard_firmware/assets/` | 效果图评审、底图与动态文字分离、冻结等待页格式和指纹、成品图和附件边界核对 | 视觉成品已有评审记录，冻结等待页离线验证通过；真机画质待验证 |
| `SPEC-DASHBOARD-015` 至 `SPEC-DASHBOARD-018` | [`优化固件 DESIGN`](AP01-1.0.2_0031-opt.bin.md) 第 7.3、7.5、7.6 节 | `features/agents_dashboard/formatting.py`、`renderer.py` | 单位边界、五位主体数字、无小数和比例方向自动测试 | 自动测试已实现；真机显示待验证 |
| `SPEC-DASHBOARD-019` 至 `SPEC-DASHBOARD-025` | [`优化固件 DESIGN`](AP01-1.0.2_0031-opt.bin.md) 第 7.2 至 7.6 节 | `features/agents_dashboard/models.py`、`renderer.py` | 四页逐字段、组图标、文字颜色和无虚假圆环的图像核对 | 自动产物已有；真机逐页验收待完成 |
| `SPEC-DASHBOARD-026` 至 `SPEC-DASHBOARD-028` | [`优化固件 DESIGN`](AP01-1.0.2_0031-opt.bin.md) 第 7.4、8 节 | `features/agents_dashboard/collector.py`、`pricing.py`、`result_package.py` | 官方来源字段、字段白名单、缓存和成品敏感内容检查 | 本机数据链已实现；发布环境检查待完成 |
| `SPEC-DASHBOARD-029` 至 `SPEC-DASHBOARD-033` | [`优化固件 DESIGN`](AP01-1.0.2_0031-opt.bin.md) 第 6.1、7.1、10.6 至 10.17、14 节 | `features/agents_dashboard_firmware/` 的原厂萌宠三个局部分支 | 概览进入详情、三详情循环、返回、一级左右导航、功率确认与全部原厂页面回归 | `FW-AGENTS-007` 已否定；`FW-AGENTS-008` 离线通过但首次安装未完成，尚无真机证据 |

## 6. 系统设置旋钮

| SPEC 条款 | DESIGN 落点 | 代码或维护落点 | 验证方法 | 当前状态 |
| --- | --- | --- | --- | --- |
| `SPEC-ROTARY-001` 至 `SPEC-ROTARY-006` | [`优化固件 DESIGN`](AP01-1.0.2_0031-opt.bin.md) 第 6.2、11 节 | `features/settings_menu_wrap/` | 四个等长修改区间、首尾直接切换、连续同向和二级菜单回归 | 已通过阶段成品自动测试与真机验收 |
| `SPEC-ROTARY-007` 至 `SPEC-ROTARY-008` | [`优化固件 DESIGN`](AP01-1.0.2_0031-opt.bin.md) 第 6.2、11 节 | `core/rotary_encoder/` | 同格反相、机械抖动、快速反转和下一完整格自动与真机验收 | 已通过阶段成品自动测试与真机验收 |

## 7. 治理与总体验收

| SPEC 条款 | DESIGN 落点 | 代码或维护落点 | 验证方法 | 当前状态 |
| --- | --- | --- | --- | --- |
| `SPEC-GOV-001` 至 `SPEC-GOV-004` | [`项目交付与 WebUI 刷机工具 DESIGN`](项目交付与WebUI刷机工具.md) 第 2、4 节 | `reference/requirements.md`、复制后的功能专属资产、发布检查 | 依赖唯一性、参考来源记录、无绝对路径运行依赖和模块归属检查 | 现有固件部分已执行；WebUI 复用拟定 |
| `SPEC-GOV-005` 至 `SPEC-GOV-008` | [`design.md`](../design.md) 第 2、3 节；[`优化固件 DESIGN`](AP01-1.0.2_0031-opt.bin.md) 第 1、4、11、12 节 | `knowledge/AP01-官方固件分析/`、固件规范、安全兼容入口、文档核对任务 | 原厂逻辑调查、固件分析路径引用、复用边界、先 DESIGN 后代码和纠偏顺序检查 | 原厂复用先行流程已写入；自动核对拟定 |
| `SPEC-ACCEPT-001` 至 `SPEC-ACCEPT-002` | 本矩阵；[`项目交付与 WebUI 刷机工具 DESIGN`](项目交付与WebUI刷机工具.md) 第 10 节 | 后续验收汇总任务 | 全条款落点、证据范围和阶段成品边界检查 | 落点已建立；总体验收未通过 |
| `SPEC-ACCEPT-003` 至 `SPEC-ACCEPT-004` | [`优化固件 DESIGN`](AP01-1.0.2_0031-opt.bin.md) 第 11、14 节 | 固件与服务端模块测试、真机验收案例 | 四页、故障切换、旋钮全路径；页面开关六类场景 | 阻塞 |
| `SPEC-ACCEPT-005` 至 `SPEC-ACCEPT-006` | [`项目交付与 WebUI 刷机工具 DESIGN`](项目交付与WebUI刷机工具.md) 第 9、10 节 | 双平台发布包、刷机记录、回刷记录和发布门禁 | 双平台完整流程、真实刷机、敏感检查、原厂回归与证据适用范围 | 阻塞 |

## 8. 覆盖结论

- 文档合同：4 条；
- 产品边界：6 条；
- MVP：9 条；
- 固件身份与产物：8 条；
- WebUI 刷机：8 条；
- 一级页面开关：7 条；
- AGENTS 看板：33 条；
- 系统设置旋钮：8 条；
- 治理：8 条；
- 总体验收：6 条；
- 版本维护：3 条；
- 合计：100 条，全部具有 DESIGN、代码或维护落点、验证方法和当前状态。

供静态核对逐项比对的条款集合如下；本段只列编号，不新增落点：

- `SPEC-DOC-001`、`SPEC-DOC-002`、`SPEC-DOC-003`、`SPEC-DOC-004`；
- `SPEC-PRODUCT-001`、`SPEC-PRODUCT-002`、`SPEC-PRODUCT-003`、
  `SPEC-PRODUCT-004`、`SPEC-PRODUCT-005`、`SPEC-PRODUCT-006`；
- `SPEC-MVP-001`、`SPEC-MVP-002`、`SPEC-MVP-003`、`SPEC-MVP-004`、
  `SPEC-MVP-005`、`SPEC-MVP-006`、`SPEC-MVP-007`、`SPEC-MVP-008`、
  `SPEC-MVP-009`；
- `SPEC-FIRMWARE-001`、`SPEC-FIRMWARE-002`、`SPEC-FIRMWARE-003`、
  `SPEC-FIRMWARE-004`、`SPEC-FIRMWARE-005`、`SPEC-FIRMWARE-006`、
  `SPEC-FIRMWARE-007`、`SPEC-FIRMWARE-008`；
- `SPEC-FLASH-001`、`SPEC-FLASH-002`、`SPEC-FLASH-003`、`SPEC-FLASH-004`、
  `SPEC-FLASH-005`、`SPEC-FLASH-006`、`SPEC-FLASH-007`、`SPEC-FLASH-008`；
- `SPEC-PAGE-001`、`SPEC-PAGE-002`、`SPEC-PAGE-003`、`SPEC-PAGE-004`、
  `SPEC-PAGE-005`、`SPEC-PAGE-006`、`SPEC-PAGE-007`；
- `SPEC-DASHBOARD-001`、`SPEC-DASHBOARD-002`、`SPEC-DASHBOARD-003`、
  `SPEC-DASHBOARD-004`、`SPEC-DASHBOARD-005`、`SPEC-DASHBOARD-006`、
  `SPEC-DASHBOARD-007`、`SPEC-DASHBOARD-008`、`SPEC-DASHBOARD-009`、
  `SPEC-DASHBOARD-010`、`SPEC-DASHBOARD-011`、`SPEC-DASHBOARD-012`、
  `SPEC-DASHBOARD-013`、`SPEC-DASHBOARD-014`、`SPEC-DASHBOARD-015`、
  `SPEC-DASHBOARD-016`、`SPEC-DASHBOARD-017`、`SPEC-DASHBOARD-018`、
  `SPEC-DASHBOARD-019`、`SPEC-DASHBOARD-020`、`SPEC-DASHBOARD-021`、
  `SPEC-DASHBOARD-022`、`SPEC-DASHBOARD-023`、`SPEC-DASHBOARD-024`、
  `SPEC-DASHBOARD-025`、`SPEC-DASHBOARD-026`、`SPEC-DASHBOARD-027`、
  `SPEC-DASHBOARD-028`、`SPEC-DASHBOARD-029`、`SPEC-DASHBOARD-030`、
  `SPEC-DASHBOARD-031`、`SPEC-DASHBOARD-032`、`SPEC-DASHBOARD-033`；
- `SPEC-ROTARY-001`、`SPEC-ROTARY-002`、`SPEC-ROTARY-003`、
  `SPEC-ROTARY-004`、`SPEC-ROTARY-005`、`SPEC-ROTARY-006`、
  `SPEC-ROTARY-007`、`SPEC-ROTARY-008`；
- `SPEC-GOV-001`、`SPEC-GOV-002`、`SPEC-GOV-003`、`SPEC-GOV-004`、
  `SPEC-GOV-005`、`SPEC-GOV-006`、`SPEC-GOV-007`、`SPEC-GOV-008`；
- `SPEC-ACCEPT-001`、`SPEC-ACCEPT-002`、`SPEC-ACCEPT-003`、
  `SPEC-ACCEPT-004`、`SPEC-ACCEPT-005`、`SPEC-ACCEPT-006`；
- `SPEC-VERSION-001`、`SPEC-VERSION-002`、`SPEC-VERSION-003`。
