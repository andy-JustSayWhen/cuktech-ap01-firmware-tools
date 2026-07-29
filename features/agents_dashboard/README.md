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

启动本机真实数据同步服务：

```shell
python3 -m features.agents_dashboard.bridge \
  --initialize-config \
  --config env/agents-dashboard-device.json

python3 -m features.agents_dashboard.bridge \
  --bind 0.0.0.0 \
  --port 8765 \
  --interval 300 \
  --config env/agents-dashboard-device.json \
  --codex-home ~/.codex \
  --cache-directory env/agents-dashboard-cache \
  --output artifacts/agents-dashboard \
  --font-directory env/fonts
```

初始化入口会在被版本控制忽略的 `env/agents-dashboard-device.json` 生成或复用设备专属配置，
随后立即退出。正常服务与固件构建只读取已经存在的配置；配置缺失时停止，禁止自动生成新身份。
换机时必须原样迁移与已刷固件配套的配置；无法取得旧配置时，新初始化的配置只适用于后续重新
制作并安装的设备专属成品。

服务把当前四页完整包写入被版本控制忽略的 `artifacts/agents-dashboard/`。完整包格式、授权
字段、页面顺序和大小上限只见 DESIGN 第 8 节。服务日志只记录不带查询字段的请求路径。启动时
无法生成新包，但已有包能由当前设备配置完整验签时，服务继续提供旧包并在健康结果中标记降级。
数据根目录和安全聚合缓存目录可以按当前服务电脑显式指定，不必固定为某个用户名或仓库路径。

设备专属实验固件只允许从已验收的 `opt-setting.bin` 构建：

```shell
python3 app/ap01_firmware.py agents-sync-build \
  --input artifacts/firmware/opt-setting.bin \
  --output artifacts/firmware/ap01-1.0.2_0031-agents-sync-experimental.bin \
  --manifest artifacts/build/agents-sync/manifest.json \
  --build-dir artifacts/build/agents-sync/payload \
  --config env/agents-dashboard-device.json \
  --url-base http://本机局域网地址:8765/a
```

构建只生成候选文件和清单，不上传、不下发、不安装。

渲染前必须从 Google Fonts 取得 Michroma Regular，并从 MiSans 官方下载页取得 Regular、
Medium、Semibold、Bold 四个字重，统一放入 `env/fonts/`。具体字体角色只见效果图评审文档
第 2 节。字体文件不进入版本控制，也不随本项目转发。

图标来源、文件对应关系和许可见 [`assets/icons/SOURCES.md`](assets/icons/SOURCES.md)。
