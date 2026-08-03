from __future__ import annotations

import hashlib
import json
import shutil
import stat
import tempfile
import unittest
from pathlib import Path

from core.firmware_image import changed_ranges
from features.primary_page_settings.delayed_row_creation import (
    BOOT_CALL_AFTER,
    MENU_DISPATCH_A,
    MENU_DISPATCH_OFFSET,
    MENU_LIMIT_OFFSET,
    MENU_LIMIT_SEVEN,
    OUTPUT_NAME,
    SETTINGS_CALLBACK_HIGH_OFFSET,
    SETTINGS_CALLBACK_HIGH_ORIGINAL,
    SETTINGS_CALLBACK_LOW_OFFSET,
    SETTINGS_CALLBACK_LOW_ORIGINAL,
    SETTINGS_CALL_AFTER,
    PageSettingsDelayedRowCreationError,
    build_page_settings_delayed_row_creation,
    simulate_page_settings_delayed_row_creation,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
STAGE = (
    REPO_ROOT
    / "artifacts/firmware/ap01-1.0.2_0031-page-settings-startup-passthrough.bin"
)


def _tool(name: str) -> Path:
    discovered = shutil.which(name)
    if discovered:
        return Path(discovered)
    return Path("/opt/homebrew/bin") / name


TOOLS = {
    "assembler": _tool("riscv64-elf-as"),
    "linker": _tool("riscv64-elf-ld"),
    "copier": _tool("riscv64-elf-objcopy"),
    "readelf": _tool("riscv64-elf-readelf"),
    "nm": _tool("riscv64-elf-nm"),
    "dumper": _tool("riscv64-elf-objdump"),
}


class PageSettingsDelayedRowCreationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not STAGE.is_file() or not all(item.is_file() for item in TOOLS.values()):
            raise unittest.SkipTest("本机缺少 A 阶段输入或设备端构建工具")

    def test_simulation_separates_boot_and_settings_callers(self) -> None:
        result = simulate_page_settings_delayed_row_creation()
        self.assertTrue(result["passed"])
        self.assertEqual(result["boot"]["caller_after"], f"0x{BOOT_CALL_AFTER:08x}")
        self.assertEqual(result["boot"]["items_created"], 7)
        self.assertFalse(result["boot"]["delayed_row_created"])
        self.assertEqual(
            result["settings_entry"]["caller_after"],
            f"0x{SETTINGS_CALL_AFTER:08x}",
        )
        self.assertEqual(result["settings_entry"]["items_created"], 8)
        self.assertTrue(result["settings_entry"]["delayed_row_created"])
        self.assertFalse(result["unknown_caller"]["delayed_row_created"])
        self.assertEqual(result["failures"], 0)

    def test_build_changes_only_payload_and_recovery_crc(self) -> None:
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            output = root / OUTPUT_NAME
            manifest = root / "manifest.json"
            result = build_page_settings_delayed_row_creation(
                STAGE,
                output,
                manifest,
                root / "build",
                **TOOLS,
                tool_revision={"commit": "test", "scoped_code_dirty": False},
            )
            document = json.loads(manifest.read_text(encoding="utf-8"))
            before = STAGE.read_bytes()
            after = output.read_bytes()
            allowed = [
                (item["start"], item["end_exclusive"])
                for item in document["allowed_ranges"]
            ]
            for difference in changed_ranges(before, after):
                self.assertTrue(
                    any(
                        start <= difference.start and difference.end <= end
                        for start, end in allowed
                    )
                )
            self.assertEqual(
                after[MENU_LIMIT_OFFSET : MENU_LIMIT_OFFSET + 2], MENU_LIMIT_SEVEN
            )
            self.assertEqual(
                after[MENU_DISPATCH_OFFSET : MENU_DISPATCH_OFFSET + 4],
                MENU_DISPATCH_A,
            )
            self.assertEqual(
                after[
                    SETTINGS_CALLBACK_HIGH_OFFSET : SETTINGS_CALLBACK_HIGH_OFFSET
                    + 4
                ],
                SETTINGS_CALLBACK_HIGH_ORIGINAL,
            )
            self.assertEqual(
                after[
                    SETTINGS_CALLBACK_LOW_OFFSET : SETTINGS_CALLBACK_LOW_OFFSET + 4
                ],
                SETTINGS_CALLBACK_LOW_ORIGINAL,
            )
            self.assertEqual(document["simulation"]["boot"]["items_created"], 7)
            self.assertEqual(document["simulation"]["settings_entry"]["items_created"], 8)
            self.assertTrue(document["validation"]["installation_allowed"])
            self.assertEqual(result.sha256, hashlib.sha256(after).hexdigest())
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o444)
            self.assertEqual(stat.S_IMODE(manifest.stat().st_mode), 0o444)

    def test_writable_stage_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            writable = root / STAGE.name
            writable.write_bytes(STAGE.read_bytes())
            with self.assertRaisesRegex(PageSettingsDelayedRowCreationError, "只读"):
                build_page_settings_delayed_row_creation(
                    writable,
                    root / OUTPUT_NAME,
                    root / "manifest.json",
                    root / "build",
                    **TOOLS,
                    tool_revision={"commit": "test", "scoped_code_dirty": False},
                )

    def test_dirty_code_is_rejected_before_input_access(self) -> None:
        with self.assertRaisesRegex(PageSettingsDelayedRowCreationError, "尚未提交"):
            build_page_settings_delayed_row_creation(
                Path("missing.bin"),
                Path(OUTPUT_NAME),
                Path("manifest.json"),
                Path("build"),
                **TOOLS,
                tool_revision={"commit": "test", "scoped_code_dirty": True},
            )


if __name__ == "__main__":
    unittest.main()
