| 名称 | 路径 | 内容 |
| --- | --- | --- |
| 原厂固件 | `artifacts/firmware/original/ap01-1.0.2_0031.bin` | 酷态科原厂 `1.0.2_0031` 固件，作为制作基线和原厂对照。 |
| 设置菜单优化固件 | `artifacts/firmware/opt-setting.bin` | 真机验收通过。仅优化系统设置一级列表的旋钮交互，支持首尾循环。 |
| AGENTS 真机观察固件 | `artifacts/firmware/ap01-1.0.2_0031-agents-observation.bin` | C1、C2 条件页排除修正版；已刷入并通过一级页面、详情进入、返回和左右切换真机验收。 |
| AGENTS 四页同步实验固件 | `artifacts/firmware/ap01-1.0.2_0031-agents-sync-experimental.bin` | 四页真实数据同步与旋钮交互；页面全屏显示，无容器边框、内边距和滑块。 |
| 完整优化固件 | `artifacts/firmware/ap01-1.0.2_0031-opt.bin` | AGENTS 四页真实数据看板与一级页面开关组合成品；页面启用状态双份保存。 |
