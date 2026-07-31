# home01-MacBookAir 与 home02-macmini 的 AGENTS 看板切换

记录日期：2026-08-01

用途：在两台服务电脑之间切换 AGENTS 看板真实数据源。技术定义只见
[`AP01 优化固件 DESIGN`](../reference/DESIGN/AP01-1.0.2_0031-opt.bin.md) 第 7 至 9 节；
本文只记录运行位置和切换步骤。

## 1. 唯一匹配条件

固件只固定服务地址。当前 `FW-AGENTS-011` 固定
`192.168.31.174:18765`，因此只会访问 home02。服务和固件均不依赖设备共享配置。

若改用 home01 的 `192.168.31.139:18765`，必须先修改对应 DESIGN，再制作并安装固定该地址的
新固件；只启动 home01 服务不能改变已刷固件的目标地址。

## 2. 已记录位置

| 项目 | home01-MacBookAir | home02-macmini |
| --- | --- | --- |
| 主机局域网地址 | `192.168.31.139` | `192.168.31.174` |
| 服务端口 | `18765` | `18765` |
| AP01 地址 | 安装记录为 `192.168.31.231`，切回后实测 | 2026-07-29 实测为 `192.168.31.231` |
| 项目目录 | `/Users/mac/Desktop/cuktech-ap01-firmware-tools` | `/Users/mac/Desktop/cuktech-ap01-firmware-tools` |
| Codex 数据根目录 | `/Users/mac/.codex` | `/Users/mac/.codex` |
| 聚合缓存 | `env/agents-dashboard-cache/` | `env/agents-dashboard-cache/` |
| 四页结果 | `artifacts/agents-dashboard/` | `artifacts/agents-dashboard/` |
| 字体目录 | `env/fonts/` | `env/fonts/` |
| 常驻任务 | 切回后按实际路径创建 | `/Users/mac/Library/LaunchAgents/com.cuktech.ap01.agents-dashboard.home02.plist` |

采集器只读取当前服务电脑用户自己的 Codex 数据根目录。四页结果包和安全聚合缓存可以重新
生成；字体需从原工作区或官方来源恢复，均不进入版本控制。

## 3. 切换服务电脑

### 3.1 停止原服务

切换前先停止当前电脑的常驻任务，确保同一固件目标地址只有一个服务进程响应。例如停止
home02：

```shell
launchctl bootout \
  "gui/$(id -u)" \
  /Users/mac/Library/LaunchAgents/com.cuktech.ap01.agents-dashboard.home02.plist
```

### 3.2 启动目标服务

```shell
cd /Users/mac/Desktop/cuktech-ap01-firmware-tools

python3 -m features.agents_dashboard.bridge \
  --bind 0.0.0.0 \
  --port 18765 \
  --interval 300 \
  --codex-home /Users/mac/.codex \
  --cache-directory env/agents-dashboard-cache \
  --output artifacts/agents-dashboard \
  --font-directory env/fonts
```

前台启动必须成功生成新包，或确认磁盘上的旧包仍能通过完整检查。

### 3.3 检查服务

```shell
curl --fail --silent --show-error \
  http://127.0.0.1:18765/health

curl --fail --silent --show-error \
  http://目标主机局域网地址:18765/health

curl --fail --silent --show-error \
  --output /tmp/ap01-agents-current.apag \
  http://目标主机局域网地址:18765/a
```

继续条件：

- 健康结果的 `ok` 为 `true`、`degraded` 为 `false`、`error` 为 `null`；
- `quota`、`reset_cards`、`profile`、`local_sessions` 均为 `true`；
- `/a` 返回的四页包能通过第 8.1 节完整检查；
- AP01 的正常后台请求到达后，`requests` 增加且 `last_request` 更新。

### 3.4 恢复常驻任务

前台检查通过后，再按目标电脑的实际程序路径、项目路径和日志路径恢复常驻任务。任务参数只
包含数据根目录、缓存目录、字体目录、结果目录、绑定地址、端口和刷新周期。

## 4. 固件地址切换门禁

如果目标电脑不能取得固件当前固定的局域网地址：

1. 先在对应 DESIGN 记录新地址和复用方案；
2. 修改固件地址区；
3. 通过全量测试、严格连续事件模拟和两次确定性构建；
4. 部署目标服务并确认 `/a` 可直接取包；
5. 按《固件制作规范》完成上传、全量回读和单次安装。
