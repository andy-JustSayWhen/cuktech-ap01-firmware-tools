"""构建并挂接一级页面开关设备端对象。"""

from __future__ import annotations

import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path

from core.firmware_image import ByteRange

from .assets import PageSettingsAsset, build_page_settings_assets


MODULE_DIR = Path(__file__).resolve().parent
ASSEMBLY_SOURCE = MODULE_DIR / "primary_page_settings.S"
PERSISTENCE_SOURCE = MODULE_DIR / "persistence.c"
XIP_DELTA = 0x9FFFF000
MENU_LIMIT_OFFSET = 0x1999B4
MENU_LIMIT_ORIGINAL = bytes.fromhex("9d47")
MENU_LIMIT_EIGHT = bytes.fromhex("a147")
MENU_DISPATCH_OFFSET = 0x1999DC
MENU_DISPATCH_ORIGINAL = bytes.fromhex("638ae70e")
SETTINGS_CALLBACK_HIGH_OFFSET = 0x0BE8CC
SETTINGS_CALLBACK_HIGH_ORIGINAL = bytes.fromhex("b7850fa0")
SETTINGS_CALLBACK_LOW_OFFSET = 0x0BE8D4
SETTINGS_CALLBACK_LOW_ORIGINAL = bytes.fromhex("93856509")
REQUIRED_SYMBOLS = (
    "ap01_page_settings_menu_dispatch",
    "ap01_page_settings_event",
    "ap01_primary_page_filter_and_switch",
    "ap01_page_settings_load_mask",
    "ap01_page_settings_save_mask",
    "ap01_page_settings_reset",
    "page_settings_background_descriptor",
    "page_settings_marker_descriptor",
    "page_settings_check_descriptor",
)


class PrimaryPageSettingsBuildError(RuntimeError):
    """一级页面开关对象或挂接字节不满足固定合同。"""


@dataclass(frozen=True)
class PrimaryPageSettingsObjects:
    objects: tuple[Path, ...]
    assets: tuple[PageSettingsAsset, ...]


def _run(command: list[Path | str]) -> None:
    try:
        completed = subprocess.run(
            [str(item) for item in command],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        raise PrimaryPageSettingsBuildError("无法启动页面开关构建工具") from error
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise PrimaryPageSettingsBuildError(f"页面开关构建失败：{detail}")


def _asset_assembly(path: Path, assets: tuple[PageSettingsAsset, ...]) -> None:
    lines = ['    .section .assets, "a", @progbits', "    .balign 4"]
    for asset in assets:
        selected = str(asset.path)
        if '"' in selected or "\n" in selected:
            raise PrimaryPageSettingsBuildError("页面开关资源路径含非法字符")
        symbol = f"page_settings_{asset.key}"
        lines.extend(
            (
                f"    .global {symbol}_descriptor",
                f"{symbol}_descriptor:",
                "    .word 0x00000119",
                "    .word 0",
                "    .word 0",
                f"    .word {symbol}_end - {symbol}_data",
                f"    .word {symbol}_data",
                "    .word 0",
                "    .word 0",
                f"{symbol}_data:",
                f'    .incbin "{selected}"',
                f"{symbol}_end:",
                "    .balign 4",
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def build_page_settings_objects(
    build_directory: Path,
    font_directory: Path,
    *,
    assembler: Path,
    compiler: Path,
) -> PrimaryPageSettingsObjects:
    """生成可由最终固件入口组合的三个目标文件。"""

    selected = build_directory.expanduser().resolve()
    selected.mkdir(parents=True, exist_ok=True)
    assets = build_page_settings_assets(font_directory, selected / "assets")
    asset_source = selected / "page-settings-assets.S"
    _asset_assembly(asset_source, assets)
    assembly_object = selected / "primary-page-settings.o"
    persistence_object = selected / "primary-page-settings-persistence.o"
    asset_object = selected / "primary-page-settings-assets.o"
    _run(
        [
            assembler,
            "-march=rv32imac",
            "-mabi=ilp32",
            "-o",
            assembly_object,
            ASSEMBLY_SOURCE,
        ]
    )
    _run(
        [
            compiler,
            "-march=rv32imac",
            "-mabi=ilp32",
            "-Os",
            "-ffreestanding",
            "-fno-builtin",
            "-fno-pic",
            "-fno-pie",
            "-fno-plt",
            "-fno-stack-protector",
            "-fno-asynchronous-unwind-tables",
            "-fno-unwind-tables",
            "-fno-jump-tables",
            "-fno-common",
            "-fno-toplevel-reorder",
            "-fno-tree-loop-distribute-patterns",
            "-fstack-usage",
            "-msmall-data-limit=0",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-c",
            PERSISTENCE_SOURCE,
            "-o",
            persistence_object,
        ]
    )
    _run(
        [
            assembler,
            "-march=rv32imac",
            "-mabi=ilp32",
            "-o",
            asset_object,
            asset_source,
        ]
    )
    return PrimaryPageSettingsObjects(
        objects=(assembly_object, persistence_object, asset_object),
        assets=assets,
    )


def _jump(source: int, target: int) -> bytes:
    offset = target - source
    if offset & 1 or not -(1 << 20) <= offset < (1 << 20):
        raise PrimaryPageSettingsBuildError("设置菜单分发跳转超出范围")
    immediate = offset & 0x1FFFFF
    word = (
        (((immediate >> 20) & 1) << 31)
        | (((immediate >> 1) & 0x3FF) << 21)
        | (((immediate >> 11) & 1) << 20)
        | (((immediate >> 12) & 0xFF) << 12)
        | 0x6F
    )
    return struct.pack("<I", word)


def _absolute_pair(target: int, register: int) -> tuple[bytes, bytes]:
    high = (target + 0x800) >> 12
    low = target - (high << 12)
    lui = ((high & 0xFFFFF) << 12) | (register << 7) | 0x37
    addi = (
        ((low & 0xFFF) << 20)
        | (register << 15)
        | (register << 7)
        | 0x13
    )
    return struct.pack("<I", lui), struct.pack("<I", addi)


def _replace(
    firmware: bytearray,
    offset: int,
    expected: bytes,
    replacement: bytes,
    label: str,
) -> ByteRange:
    if len(expected) != len(replacement):
        raise PrimaryPageSettingsBuildError(f"{label}长度不一致")
    end = offset + len(expected)
    if bytes(firmware[offset:end]) != expected:
        raise PrimaryPageSettingsBuildError(f"{label}旧字节不匹配")
    firmware[offset:end] = replacement
    return ByteRange(offset, end)


def apply_page_settings_patches(
    firmware: bytearray,
    symbols: dict[str, int],
) -> list[ByteRange]:
    """把已链接入口挂到当前版本的四个固定位置。"""

    missing = [name for name in REQUIRED_SYMBOLS if name not in symbols]
    if missing:
        raise PrimaryPageSettingsBuildError(
            f"页面开关载荷缺少符号：{', '.join(missing)}"
        )
    high, low = _absolute_pair(symbols["ap01_page_settings_event"], 11)
    return [
        _replace(
            firmware,
            MENU_LIMIT_OFFSET,
            MENU_LIMIT_ORIGINAL,
            MENU_LIMIT_EIGHT,
            "设置菜单数量",
        ),
        _replace(
            firmware,
            MENU_DISPATCH_OFFSET,
            MENU_DISPATCH_ORIGINAL,
            _jump(
                XIP_DELTA + MENU_DISPATCH_OFFSET,
                symbols["ap01_page_settings_menu_dispatch"],
            ),
            "设置菜单新增行分发",
        ),
        _replace(
            firmware,
            SETTINGS_CALLBACK_HIGH_OFFSET,
            SETTINGS_CALLBACK_HIGH_ORIGINAL,
            high,
            "设置键值包装地址高位",
        ),
        _replace(
            firmware,
            SETTINGS_CALLBACK_LOW_OFFSET,
            SETTINGS_CALLBACK_LOW_ORIGINAL,
            low,
            "设置键值包装地址低位",
        ),
    ]
