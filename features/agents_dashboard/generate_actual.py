from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .collector import collect_snapshot
from .renderer import render_all


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = (
    PROJECT_ROOT / "reference" / "image" / "DESIGN" / "AP01-AGENTS看板" / "真实数据"
)
DEFAULT_FONTS = PROJECT_ROOT / "env" / "fonts"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(128 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generate(output: Path = DEFAULT_OUTPUT, font_directory: Path = DEFAULT_FONTS) -> dict:
    snapshot = collect_snapshot()
    written = render_all(snapshot, output, font_directory)
    snapshot_path = output / "snapshot.json"
    snapshot_path.write_text(
        json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    files = [
        {
            "name": name,
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for name, path in written.items()
    ]
    readme = [
        "# AGENTS 看板本机真实数据对照",
        "",
        f"- 生成时间：`{snapshot.generated_at}`",
        "- 画布：`320×240`",
        "- 字体：使用 MiSans 字体",
        "- 数据：只保存聚合值，不保存提示词、回复正文、登录信息或本机路径",
        "- 周额度与重置卡：直接读取 Codex 官方接口，字段解析参考 Cockpit Tools",
        "- 今日消耗：直接扫描 Codex 本机会话记录，增量算法固定为 CC Switch 3.16.1",
        "- 近 30 天、活动洞察与常用插件：直接读取 Codex 个人统计，字段映射与 Codex 桌面端一致",
        "- 运行依赖：不要求安装 Cockpit Tools、CC Switch 或 Codex 桌面端",
        "- 用途：与已确认效果图比较；不是固件资源，也不是 PNG 真机验证结果",
        "",
        "## 文件",
        "",
        "| 文件 | 字节数 | SHA-256 |",
        "| --- | ---: | --- |",
    ]
    readme.extend(
        f"| `{item['name']}` | {item['bytes']:,} | `{item['sha256']}` |"
        for item in files
    )
    readme.extend(
        [
            "",
            "数据快照见 [`snapshot.json`](snapshot.json)。",
            "",
        ]
    )
    (output / "README.md").write_text("\n".join(readme), encoding="utf-8")
    return snapshot.to_dict()


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 AP01 AGENTS 看板本机真实数据对照图")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--font-directory", type=Path, default=DEFAULT_FONTS)
    arguments = parser.parse_args()
    snapshot = generate(arguments.output, arguments.font_directory)
    print(
        json.dumps(
            {
                "generated_at": snapshot["generated_at"],
                "weekly_remaining_percent": snapshot["weekly_remaining_percent"],
                "today_total_tokens": snapshot["today"]["total_tokens"],
                "last_30d_tokens": snapshot["last_30d_tokens"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
