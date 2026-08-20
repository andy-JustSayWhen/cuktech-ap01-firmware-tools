# 固件制作 Docker 工具

本目录是 Windows 与 macOS 共用的固件制作环境，使用方法见 [`固件制作 Docker 环境`](../../reference/DESIGN/固件制作Docker环境.md)。

工具来源：

- RISC-V GCC 16.1.0 与 Binutils 2.46.1：`riscv-collab/riscv-gnu-toolchain` 的 `2026.07.15` Linux x86-64 发布文件。
- Gifsicle 1.96：`kohler/gifsicle` 的 `1.96` 源码。本项目成品使用 Apple 的排序行为制作，以复现已验收动图字节。
- FFmpeg 8.1.1：`ffmpeg.org` 的 `8.1.1` 源码。
- Python 程序库安装包：Python Package Index（Python 程序库的官方发布站点）对应版本文件，文件指纹已与站点记录逐一核对。

各程序许可原文位于 `licenses/`；项目仅使用和再分发这些构建工具，不把它们链接进 AP01 固件。
