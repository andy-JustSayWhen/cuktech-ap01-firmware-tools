| 名称 | 路径 | 内容 |
| --- | --- | --- |
| 原厂固件 | `artifacts/firmware/original/ap01-1.0.2_0031.bin` | 酷态科原厂 `1.0.2_0031` 固件，作为制作基线和原厂对照。 |
| 设置菜单优化固件 | `artifacts/firmware/opt-setting.bin` | 真机验收通过。仅优化系统设置一级列表的旋钮交互，支持首尾循环。 |
| AGENTS 历史真机观察固件 | `artifacts/firmware/ap01-1.0.2_0031-agents-observation.bin` | 旧页面注册方案曾通过有限交互验收；不作为当前设计输入，不再安装。 |
| AGENTS 历史四页同步实验固件 | `artifacts/firmware/ap01-1.0.2_0031-agents-sync-experimental.bin` | 当前文件与首次安装件同名但指纹不同；不作为当前设计输入，不再安装。 |
| 一级页面开关失败成品 | `artifacts/firmware/ap01-1.0.2_0031-opt.bin` | 卡在开机动画，禁止安装；设备已回刷上一份 AGENTS 四页同步实验固件。 |
| 设置列表历史空挂接观察固件 | `artifacts/firmware/ap01-1.0.2_0031-page-settings-hook-observation.bin` | 旧四页成品上的空挂接曾通过启动和联网；不作为当前设计输入，不再安装。 |
| 原厂详情兼容失败成品 | `artifacts/firmware/ap01-1.0.2_0031-agents-detail-compat-observation.bin` | 普通确认误入时间设定，“返回”触发重启，禁止安装。 |
| 原厂确认键兼容失败成品 | `artifacts/firmware/ap01-1.0.2_0031-agents-confirm-compat-observation.bin` | “返回”仍触发重启，禁止安装；设备已回刷 `opt-setting.bin`。 |
| AGENTS 九对象覆盖层失败成品 | `artifacts/firmware/ap01-1.0.2_0031-agents-pet-overlay-observation.bin` | 菜单“返回”触发重启，禁止安装；设备已回刷 `opt-setting.bin`。 |
| AGENTS 原厂萌宠控件复用失败成品 | `artifacts/firmware/ap01-1.0.2_0031-agents-stock-pet-reuse-observation.bin` | 日历详情无法返回一级页面，禁止安装；设备已回刷 `opt-setting.bin`。 |
| AGENTS 原厂交互分派兼容失败成品 | `artifacts/firmware/ap01-1.0.2_0031-agents-stock-dispatch-observation.bin` | 页面切换入口与状态字段证据不成立，禁止安装；从未刷入。 |
