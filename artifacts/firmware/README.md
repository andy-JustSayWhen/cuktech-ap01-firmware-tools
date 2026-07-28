| 名称 | 路径 | 内容 |
| --- | --- | --- |
| 原厂固件 | `artifacts/firmware/original/ap01-1.0.2_0031.bin` | 酷态科原厂 `1.0.2_0031` 固件，作为制作基线和原厂对照。 |
| 设置菜单优化固件 | `artifacts/firmware/opt-setting.bin` | 真机验收通过。仅优化系统设置一级列表的旋钮交互，支持首尾循环。 |
| AGENTS 真机观察固件 | `artifacts/firmware/ap01-1.0.2_0031-agents-observation.bin` | C1、C2 条件页排除修正版；已刷入并通过一级页面、详情进入、返回和左右切换真机验收。 |
| AGENTS 四页同步实验固件 | `artifacts/firmware/ap01-1.0.2_0031-agents-sync-experimental.bin` | 四页真实数据同步与旋钮交互；页面全屏显示，无容器边框、内边距和滑块。 |
| 一级页面开关失败成品 | `artifacts/firmware/ap01-1.0.2_0031-opt.bin` | 卡在开机动画，禁止安装；设备已回刷上一份 AGENTS 四页同步实验固件。 |
| 设置列表空挂接观察固件 | `artifacts/firmware/ap01-1.0.2_0031-page-settings-hook-observation.bin` | 已刷入；启动、联网和看板取包通过，待确认原厂 7 项设置交互。 |
| 原厂详情兼容失败成品 | `artifacts/firmware/ap01-1.0.2_0031-agents-detail-compat-observation.bin` | 普通确认误入时间设定，“返回”触发重启，禁止安装。 |
| 原厂确认键兼容失败成品 | `artifacts/firmware/ap01-1.0.2_0031-agents-confirm-compat-observation.bin` | “返回”仍触发重启，禁止安装；设备已回刷 `opt-setting.bin`。 |
| AGENTS 九对象覆盖层失败成品 | `artifacts/firmware/ap01-1.0.2_0031-agents-pet-overlay-observation.bin` | 菜单“返回”触发重启，禁止安装；设备已回刷 `opt-setting.bin`。 |
| AGENTS 原厂萌宠控件复用观察固件 | `artifacts/firmware/ap01-1.0.2_0031-agents-stock-pet-reuse-observation.bin` | 不新增界面对象，复用原厂萌宠动图控件；已安装并重新上线，待物理验收。 |
