# 固件制作 Docker 环境

## 1. 对应规格

本文实现 [`SPEC-TOOLS-001` 至 `SPEC-TOOLS-004`](../SPEC.md#跨固件制作环境)，对应 [`BRIEF-TOOLS-001`](../brief.md#brief-tools-001-固件制作工具随项目提供)。

为了让 Windows 和 macOS 用户都能在构建固件的时候，提前一次性把所有的固件构建工具都下载完整且不报版本等错误，这里选择把所有的构建工具制作成 Docker 容器。本文即是这个容器的技术设计文档。

## 2. 文件与职责

| 路径 | 职责 |
| --- | --- |
| `tools/docker/Dockerfile` | 定义 Ubuntu 24.04 环境、系统程序和项目固定程序库。 |
| `tools/docker/toolchain/` | 保存已核对版本的 Linux x86-64 固件制作程序。 |
| `tools/docker/python-wheels/` | 保存 Python 程序库安装包，制作镜像时不再从网络逐个下载。 |
| `tools/docker/check-tools.sh` | 核对所有固定工具的版本，任一不符时返回失败。 |
| `tools/ap01-tools.ps1` | Windows 入口。 |
| `tools/ap01-tools.sh` | macOS 入口。 |

## 3. 镜像制作

两个入口都以项目根目录为制作范围，使用 `tools/docker/Dockerfile` 制作名为 `cuktech-ap01-build-tools:1.0` 的本地镜像。工具文件改变后，入口根据制作范围重新制作镜像；工具文件不变时直接复用现有镜像。

镜像采用 Linux x86-64。Windows 的 Docker Desktop 直接运行；Apple 芯片的 macOS 由 Docker Desktop 使用处理器兼容功能运行。这样两个宿主系统实际调用的是相同二进制文件。

## 4. 命令转交和目录

入口把项目根目录挂载为 `/workspace`，工作目录固定为 `/workspace`，并把调用入口后的全部参数原样交给容器。未给参数时执行工具版本检查；给出参数时先检查版本，再执行指定命令。

镜像内 Git 使用自动换行识别，使 Windows 的 CRLF 文件和 macOS 的 LF 文件都能按仓库原始内容判断修改状态，避免把宿主系统换行差异误报为制作代码未提交。

镜像复制工具脚本后会统一转换为 Linux 换行，确保 Windows 工作区的脚本能够被容器直接执行。

镜像复制 `toolchain/` 后，必须明确为 `bin/` 中的命令和 `libexec/` 中的编译器内部程序设置执行权限。不得依赖宿主文件系统、解压程序或 Git 是否保留权限位；否则工具文件即使校验值正确，也会在容器内因不能执行而停止构建。

制作镜像或运行构建命令出现“没有执行权限”或返回 `126` 时，先核对上述两类文件的执行权限和 `tools/docker/Dockerfile` 的设置，再检查工具版本与文件指纹。这个顺序在 Windows 和 macOS 相同；不得仅凭宿主系统或处理器类型推断 Docker 不兼容。

容器不保存需要交付的文件。命令写入 `/workspace` 的文件立即出现在宿主项目目录中。

## 5. 固定版本

版本唯一清单仍为 [`requirements.md`](../requirements.md)。`check-tools.sh` 逐项读取版本输出并核对 Gifsicle 1.96、FFmpeg 8.1.1、RISC-V GCC 16.1.0、RISC-V Binutils 2.46.1、Pillow 12.2.0 和 Requests 2.x。版本核对后还要实际把一个最小 C 文件编译成 RISC-V 目标文件，确认编译器主程序、内部编译程序、汇编器和运行库可以共同工作。

## 6. 完成标准

1. Windows 入口可以制作镜像并通过全部版本检查。
2. 同一镜像可以运行项目自动测试和个人固件制作命令。
3. 使用镜像制作的固定测试固件与已验收文件逐字节一致。
4. 工具缺失或版本被替换时，检查脚本返回失败。
