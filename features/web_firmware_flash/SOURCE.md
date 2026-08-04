# 参考实现来源

本功能的小米授权、加密请求、对象上传、分发地址转换和正式安装调用顺序，来源于参考项目
`/Users/mac/Desktop/cuktech-screen-controller` 的提交
`c3ac158382f56e520bd7565d1fb2553152e4bc2f`。

已逐行核对的来源文件：

- `mi_login.py`
- `mi_cloud.py`
- `ap01_custom_ota.py`
- `ap01_install_firmware.py`

本项目没有运行时读取参考项目目录；只保留网页刷机所需接口，并增加唯一目标、脱敏身份、完整对象
回读、冻结成品和单次安装门禁。具体产品行为只见
[`项目交付与 WebUI 刷机工具 DESIGN`](../../reference/DESIGN/项目交付与WebUI刷机工具.md)。
