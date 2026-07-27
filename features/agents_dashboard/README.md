# AGENTS 看板服务端渲染模块

本模块按
[`reference/DESIGN/AP01-1.0.2_0031-opt.bin.md` 第 7 节](../../reference/DESIGN/AP01-1.0.2_0031-opt.bin.md#7-agents-看板页面)
采集本机聚合数据并生成四张 320×240 对照图。

用户可见字段口径只见
[`reference/SPEC.md` 第 4.2 节](../../reference/SPEC.md#42-看板字段口径)；数据清单、原始
字段、直接来源、采集方法和安全边界只见
[`DESIGN` 第 7.4 节](../../reference/DESIGN/AP01-1.0.2_0031-opt.bin.md#74-本机真实数据采集)；
模型单价与费用公式只见
[`Codex 模型 API 计费表`](../../reference/Codex-模型API计费表.md)。

实现依据：

- Cockpit Tools：`jlcodes99/cockpit-tools` 的 `src-tauri/src/modules/codex_quota.rs`；
- CC Switch：`farion1231/cc-switch` 的 `v3.16.1` 标签中
  `src-tauri/src/services/session_usage_codex.rs` 与
  `src-tauri/src/services/usage_stats.rs`；
- Codex 桌面端：本机应用资源中的个人统计请求与字段映射。

运行：

```shell
python3 -m features.agents_dashboard.generate_actual
```

渲染前必须从 MiSans 官方下载页取得 Light、Regular、Medium 三个字重，并放入
`env/fonts/`。本模块生成的图片使用 MiSans 字体；字体文件不进入版本控制，也不随本项目
转发。

图标来源、文件对应关系和许可见 [`assets/icons/SOURCES.md`](assets/icons/SOURCES.md)。
