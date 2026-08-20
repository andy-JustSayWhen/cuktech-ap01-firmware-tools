# AGENTS 看板服务

本模块采集当前电脑的安全汇总数据，渲染四张 320×240 双帧画面，生成完整结果包并通过局域网接口 `/a` 提供给 AP01。字段、失败行为和安全限制见 [`ap01-1.0.2_0031-opt.bin 功能规格`](../../reference/SPEC/ap01-1.0.2_0031-opt.bin.md)，实现详见 [`ap01-1.0.2_0031-opt.bin 技术实现`](../../reference/DESIGN/ap01-1.0.2_0031-opt.bin技术实现/ap01-1.0.2_0031-opt.bin技术实现.md)。

## 运行

```shell
python3 -m features.agents_dashboard.bridge \
  --bind 0.0.0.0 \
  --port 18765 \
  --interval 300 \
  --codex-home ~/.codex
```

服务启动后核对：

```shell
curl --fail --silent --show-error http://127.0.0.1:18765/health
curl --fail --silent --show-error --output /tmp/ap01-agents.apag http://127.0.0.1:18765/a
```

首次采集失败时，只有现存结果包通过完整解码才能继续提供旧结果。服务不输出提示词、回复正文、登录凭据或本机私有路径。

## 资源

字体原件和运行副本位置见 [`fonts/README.md`](../../fonts/README.md)；图标来源和许可见 [`assets/icons/SOURCES.md`](assets/icons/SOURCES.md)。 macOS 最终版的运行包固定保存在 `~/Library/Application Support/Cuktech/AP01/agents-dashboard/`，安全汇总缓存固定保存在 `~/Library/Caches/Cuktech/AP01/agents-dashboard/`。
