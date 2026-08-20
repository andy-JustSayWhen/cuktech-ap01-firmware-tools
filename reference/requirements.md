# AP01 优化固件依赖清单

本文是项目依赖的唯一清单。

| 名称 | 作用 |
| --- | --- |
| macOS | 用于固件制作、自动测试和看板服务；固件制作通过项目 Docker 镜像执行。 |
| Windows | 用于固件制作和自动测试；通过项目 Docker 镜像执行。 |
| Docker Desktop（在电脑上运行隔离 Linux 环境的程序） | Windows 与 macOS 固件制作要求可运行 Linux x86-64 镜像；已实测客户端和服务端 `29.5.3` 与 macOS 上的 `29.7.2` 均可完成本项目固件制作。 |
| Ubuntu 24.04（镜像内的基础 Linux 系统） | 固定为固件制作镜像的基础系统。 |
| GCC 运行库（让镜像内编译器能够启动的数学和压缩程序库） | 镜像安装 Ubuntu 24.04 提供的 `libgmp10`、`libmpc3`、`libmpfr6`、`libzstd1` 和 `zlib1g`。 |
| Python | 要求 `3.9` 或更高版本，当前实测为 `3.13.0`；用于运行 `app/`、`core/`、`features/` 中的程序和测试。 |
| Cryptography（用于生成加密连接证书的程序库） | 当前实测为 `50.0.0`；用于本机固件服务生成并加载设备安装所需的自签名证书。 |
| Git（记录文件版本的工具） | 命令行中必须能直接运行 `git`；用于记录构建时的提交和代码修改状态。 |
| 时区数据 | Python 必须能读取 `Asia/Shanghai`；用于计算今日消耗、重置时间和报告时间。 |
| Pillow（处理图片的程序库） | 当前实测为 `12.2.0`；用于绘制四页看板、生成设备动图、检查图片和制作内置等待画面。 |
| Python 标准库 | 随 Python 提供，无需单独安装；支持其余 Python 程序。 |
| Requests（替 Python 处理网页请求并自带可信证书清单的程序库） | 版本不低于 `2.31` 且低于 `3`；安装到项目内 `.venv`，用于小米账号扫码登录、云端查询和固件下载。 |
| `.venv` | 项目内 Python 运行环境，由 AI 按 `features/official_firmware_source/requirements.txt` 创建；不得引用项目目录外的证书文件。 |
| `tools/docker/python-wheels/` | 保存镜像内固定 Python 程序库的安装包，制作镜像时不得从网络另选版本。 |
| 小米云登录态 | 没有可用登录态时，由本项目生成二维码；用户用拥有目标 AP01 的米家账号扫码确认后自动保存到 `env/mi-cloud.env`，用于查询和下载 AP01 官方固件，不得提交。 |
| 小米云文件存储和 AP01 在线更新接口 | 由本项目 `features/firmware_installation/` 调用；用于上传固件、完整回读核对、向唯一 AP01 下发安装和查询更新状态。 |
| Gifsicle（无损整理动图的工具） | 固定为 `1.96`；用于缩小原厂内置动图，为设备端程序腾出固定空间。 |
| FFmpeg（独立解码画面的工具） | 固定为 `8.1.1`；用于核对缩小前后的每帧画面是否一致。 |
| RISC-V Binutils（生成和检查设备端程序的工具组） | 固定为 `2.46.1`；必须提供 `riscv64-elf-as`、`ld`、`objcopy`、`objdump`、`nm` 和 `readelf`。 |
| RISC-V GCC（把 C 代码编译成设备指令的编译器） | 固定为 `16.1.0`；用于编译看板下载、校验和页面采用程序。 |
| `tools/docker/toolchain/` | 保存上述 Gifsicle、FFmpeg、RISC-V GCC 和 RISC-V Binutils 的 Linux x86-64 成品，由 Windows 与 macOS 共用。 |
| `artifacts/firmware/original/ap01-1.0.2_0031.bin` | 必须存在并保持只读；用于核对官方固件身份和制作设置菜单固件。 |
| `artifacts/firmware/original/ap01-<云端版本>.bin` | 查询并下载最新官方固件时动态生成并保持只读；新版本在固定基线更新前不得用于制作或刷入。 |
| `artifacts/firmware/ap01-1.0.2_0031-opt-setting.bin` | 必须存在并保持只读；用于制作公开优化固件和个人固件。 |
| `artifacts/firmware/ap01-1.0.2_0031-opt.bin` | 必须存在并保持只读，不含用户地址；用于公开发布和一致性检查。 |
| `fonts/MiSans-Regular.ttf` | 看板正文字体原件。 |
| `fonts/MiSans-Medium.ttf` | 看板辅助字体原件。 |
| `fonts/MiSans-Semibold.ttf` | 看板重点字体原件。 |
| `fonts/MiSans-Bold.ttf` | 看板标题与主数字字体原件。 |
| `features/agents_dashboard/assets/icons/` | 提供看板图标，必须保留许可说明。 |
| [`knowledge/Codex-模型API计费表.md`](../knowledge/Codex-模型API计费表.md) | 计算当日会话费用，必须与计费实现和自动测试一致。 |
| `env/agents-dashboard.env` | 记录 1～10 个局域网服务地址和共用端口；从示例文件复制，被 Git 忽略，文件权限为 `0600`；填写规则只见[技术实现第 9.3 节](DESIGN/ap01-1.0.2_0031-opt.bin技术实现/ap01-1.0.2_0031-opt.bin技术实现.md#93-地址配置与两种固件)。 |
| `env/mi-cloud.env` | 可选；由扫码登录命令自动创建或更新，保存本机小米云查询官方固件所需账号字段，被 Git 忽略，文件权限为 `0600`。 |
| `artifacts/official-firmware/xiaomi-login-qr.png` | 扫码登录命令生成的临时二维码；只供当前登录使用，位于项目内，不得提交。 |
| `~/Library/Application Support/Cuktech/AP01/firmware/` | 保存个人固件、制作记录和页面操作模拟报告，当前用户必须可写。 |
| Codex 登录数据 | `auth.json` 必须包含可用的登录凭据和账号标识；用于读取周剩余额度、重置卡和近 30 天统计。 |
| Codex 本地会话记录 | 服务必须能读取当前用户的会话目录；用于汇总当日输入、输出、缓存和请求数。 |
| ChatGPT 网络服务 | 必须能通过 HTTPS（网页使用的加密连接）访问 `chatgpt.com`；用于读取额度、重置卡和个人统计。 |
| `~/Library/Application Support/Cuktech/AP01/agents-dashboard-service/` | macOS 默认独立部署目录；含服务代码、字体、`service-output/` 和 `service-cache/`，当前用户必须可写。 |
| 局域网 | 电脑和 AP01 必须互相可达，系统必须允许 Python 监听配置端口；设备请求 `/a` 后由电脑返回完整四页结果包。 |
| AP01 个人固件 | 必须写入至少一个当前可达的服务地址，让设备知道从哪台电脑获取看板数据。 |
| [`AP01 固件版本、结构与校验`](../knowledge/AP01-官方固件分析/固件版本、结构与校验.md) | 定义三份固件的固定长度和文件指纹，用于核对固件身份。 |
