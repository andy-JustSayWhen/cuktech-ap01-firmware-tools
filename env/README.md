# 本机配置

本文件夹存放运行和检查项目时需要使用、但不能提交到仓库的本机数据。

看板地址配置的变量含义和使用规则只见 [`技术实现第 9.3 节`](../reference/DESIGN/ap01-1.0.2_0031-opt.bin技术实现/ap01-1.0.2_0031-opt.bin技术实现.md#93-地址配置与两种固件)。 `agents-dashboard.env.example` 是空白格式，`agents-dashboard.env` 保存本机实际数据并被版本控制忽略。

小米云官方固件查询可使用 `mi-cloud.env.example` 复制出 `mi-cloud.env`。该文件保存本机登录态，只供 `official-firmware-info` 和 `official-firmware-download` 使用，并被版本控制忽略。
