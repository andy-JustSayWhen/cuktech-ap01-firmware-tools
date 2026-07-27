# AGENTS 看板服务端渲染模块

本模块按
[`reference/DESIGN/AP01-1.0.2_0031-opt.bin.md` 第 7 节](../../reference/DESIGN/AP01-1.0.2_0031-opt.bin.md#7-agents-看板页面)
采集本机聚合数据并生成四张 320×240 对照图。

数据取得方式：

- 一周额度和重置卡直接读取 Codex 官方接口，字段解析参考 Cockpit Tools；
- 今日消耗直接扫描 Codex 本机会话记录，增量算法固定为 CC Switch 3.16.1 的实现；
- 近 30 天每日用量、活动洞察和常用插件直接读取 Codex 个人统计，字段映射与 Codex 桌面端
  一致；
- 三个参考应用都不是安装依赖，采集器不读取它们的页面、缓存或数据库；
- 官方接口的安全聚合缓存写入被版本控制忽略的 `env/agents-dashboard-cache/`，不保存登录
  凭据、账号标识或原始响应。

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
