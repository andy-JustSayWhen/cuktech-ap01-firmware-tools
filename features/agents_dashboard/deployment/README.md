# AGENTS 看板常驻部署

服务端部署后必须独立于本项目运行：删除本项目，设备取包不受影响。

| 平台 | 部署方式 |
| --- | --- |
| Windows | `tools/deploy-agents-dashboard.ps1`：复制服务代码、字体和图标到用户指定目录（无要求时默认 `%LOCALAPPDATA%\Cuktech\AP01\agents-dashboard-service`），生成启动脚本，注册当前用户登录时自启的计划任务 |
| macOS | `tools/deploy-agents-dashboard.sh`：复制服务代码、字体和图标到独立目录，生成并检查登录自启动文件 |

Windows 部署目录可以包含空格；生成的启动脚本会将各目录参数作为完整路径传入服务。

使用范围、完整命令、完成标准和故障处理只见 [`如何部署服务端`](../../../SOP/如何部署服务端.md)。部署运行参数和数据来源见 [`ap01-1.0.2_0031-opt.bin 技术实现` 第 9 节](../../../reference/DESIGN/ap01-1.0.2_0031-opt.bin技术实现/ap01-1.0.2_0031-opt.bin技术实现.md#9-通过局域网自动更新看板)。

模板和脚本都不包含登录态、设备信息、固定用户目录或本机网络地址。部署时必须替换模板字段，并使用当前电脑自己的 Codex 登录状态和本地会话目录（`~/.codex`，不随部署复制）。

## Windows

默认目录为 `%LOCALAPPDATA%\Cuktech\AP01\agents-dashboard-service`。在项目根目录执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/deploy-agents-dashboard.ps1 `
  -Port 18765 `
  -IntervalSeconds 300 `
  -Start
```

脚本完成复制、注册和健康检查。若指定其他目录，额外传入 `-TargetDir "<部署路径>"`。服务的代码、字体、运行数据和缓存均位于部署目录；当前用户的 Codex 登录状态仍保留在用户主目录。

## macOS

默认目录为 `~/Library/Application Support/Cuktech/AP01/agents-dashboard-service`。在项目根目录执行：

```bash
chmod +x tools/deploy-agents-dashboard.sh
tools/deploy-agents-dashboard.sh --start
```

服务代码、字体、运行数据和缓存都放入这个目录；不要复用项目中的临时结果包。
