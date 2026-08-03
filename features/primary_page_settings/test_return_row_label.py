from __future__ import annotations

import hashlib
import json
import shutil
import stat
import tempfile
import unittest
from pathlib import Path

from core.firmware_image import changed_ranges
from features.primary_page_settings.return_row_label import (
    MENU_DISPATCH_A,
    MENU_DISPATCH_OFFSET,
    MENU_LIMIT_OFFSET,
    MENU_LIMIT_SEVEN,
    OUTPUT_NAME,
    RETURN_LABEL_HIGH_OFFSET,
    RETURN_LABEL_LOW_OFFSET,
    ROW_LABEL,
    SETTINGS_CALLBACK_HIGH_OFFSET,
    SETTINGS_CALLBACK_HIGH_ORIGINAL,
    SETTINGS_CALLBACK_LOW_OFFSET,
    SETTINGS_CALLBACK_LOW_ORIGINAL,
    STAGE_MD5,
    STAGE_SHA256,
    STAGE_SIZE,
    PageSettingsReturnRowLabelError,
    _decode_address_pair,
    build_page_settings_return_row_label,
    simulate_page_settings_return_row_label,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
STAGE = (
    REPO_ROOT
    / "artifacts/firmware"
    / "ap01-1.0.2_0031-page-settings-startup-passthrough.bin"
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


class PageSettingsReturnRowLabelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not STAGE.is_file() or not all(item.is_file() for item in TOOLS.values()):
            raise unittest.SkipTest("本机缺少 A 阶段输入或设备端构建工具")

    def test_simulation_preserves_seven_items_and_stock_return_press(self) -> None:
        result = simulate_page_settings_return_row_label()
        self.assertTrue(result["passed"])
        self.assertEqual(result["item_count"], 7)
        self.assertEqual(result["states"], list(range(48, 55)))
        self.assertEqual(result["last_row_label"], ROW_LABEL)
        self.assertEqual(result["last_row_press"], "stock-return")
        self.assertEqual(result["list_objects_added"], 0)
        self.assertFalse(result["settings_callback_changed"])
        self.assertFalse(result["physical_acceptance_replaced"])

    def test_build_changes_only_payload_label_pointer_and_recovery_crc(self) -> None:
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            output = root / OUTPUT_NAME
            manifest = root / "manifest.json"
            result = build_page_settings_return_row_label(
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
                after[MENU_DISPATCH_OFFSET : MENU_DISPATCH_OFFSET + 4], MENU_DISPATCH_A
            )
            self.assertEqual(
                after[
                    SETTINGS_CALLBACK_HIGH_OFFSET : SETTINGS_CALLBACK_HIGH_OFFSET + 4
                ],
                SETTINGS_CALLBACK_HIGH_ORIGINAL,
            )
            self.assertEqual(
                after[
                    SETTINGS_CALLBACK_LOW_OFFSET : SETTINGS_CALLBACK_LOW_OFFSET + 4
                ],
                SETTINGS_CALLBACK_LOW_ORIGINAL,
            )
            label_address = _decode_address_pair(
                after[RETURN_LABEL_HIGH_OFFSET : RETURN_LABEL_HIGH_OFFSET + 4],
                after[RETURN_LABEL_LOW_OFFSET : RETURN_LABEL_LOW_OFFSET + 4],
            )
            self.assertEqual(
                label_address,
                int(document["payload"]["label_runtime_address"], 16),
            )
            self.assertEqual(document["payload"]["label"], ROW_LABEL)
            self.assertEqual(document["payload"]["function_calls"], 0)
            self.assertTrue(document["simulation"]["passed"])
            self.assertTrue(document["validation"]["installation_allowed"])
            self.assertEqual(result.sha256, hashlib.sha256(after).hexdigest())
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o444)
            self.assertEqual(stat.S_IMODE(manifest.stat().st_mode), 0o444)

    def test_writable_stage_is_rejected_before_build(self) -> None:
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            writable = root / STAGE.name
            writable.write_bytes(STAGE.read_bytes())
            self.assertEqual(len(writable.read_bytes()), STAGE_SIZE)
            self.assertEqual(
                hashlib.sha256(writable.read_bytes()).hexdigest(), STAGE_SHA256
            )
            self.assertEqual(hashlib.md5(writable.read_bytes()).hexdigest(), STAGE_MD5)
            with self.assertRaisesRegex(PageSettingsReturnRowLabelError, "只读"):
                build_page_settings_return_row_label(
                    writable,
                    root / OUTPUT_NAME,
                    root / "manifest.json",
                    root / "build",
                    **TOOLS,
                    tool_revision={"commit": "test", "scoped_code_dirty": False},
                )

    def test_dirty_code_is_rejected_before_input_access(self) -> None:
        with self.assertRaisesRegex(PageSettingsReturnRowLabelError, "尚未提交"):
            build_page_settings_return_row_label(
                Path("missing.bin"),
                Path(OUTPUT_NAME),
                Path("manifest.json"),
                Path("build"),
                **TOOLS,
                tool_revision={"commit": "test", "scoped_code_dirty": True},
            )


if __name__ == "__main__":
    unittest.main()
