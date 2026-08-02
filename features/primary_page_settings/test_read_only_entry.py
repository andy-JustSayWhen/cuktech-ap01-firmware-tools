from __future__ import annotations

import hashlib
import json
import shutil
import stat
import tempfile
import unittest
from pathlib import Path

from core.firmware_image import changed_ranges
from features.primary_page_settings.read_only_entry import (
    MENU_DISPATCH_OFFSET,
    MENU_LIMIT_EIGHT,
    MENU_LIMIT_OFFSET,
    OUTPUT_NAME,
    SETTINGS_CALLBACK_HIGH_OFFSET,
    SETTINGS_CALLBACK_HIGH_ORIGINAL,
    SETTINGS_CALLBACK_LOW_OFFSET,
    SETTINGS_CALLBACK_LOW_ORIGINAL,
    STAGE_MD5,
    STAGE_SHA256,
    STAGE_SIZE,
    PageSettingsReadOnlyEntryError,
    build_page_settings_read_only_entry,
    simulate_page_settings_read_only_entry,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
STAGE = (
    REPO_ROOT
    / "env/firmware-inputs"
    / STAGE_SHA256
    / "opt-setting.bin"
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


class PageSettingsReadOnlyEntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not STAGE.is_file() or not all(item.is_file() for item in TOOLS.values()):
            raise unittest.SkipTest("本机缺少只读设置阶段输入或设备端构建工具")
        if shutil.which("gifsicle") is None or shutil.which("ffmpeg") is None:
            raise unittest.SkipTest("本机缺少固定动图整理或独立解码工具")

    def test_strict_simulation_covers_all_depth_five_sequences(self) -> None:
        result = simulate_page_settings_read_only_entry()
        self.assertTrue(result["passed"])
        self.assertEqual(result["directed_scenarios"], 8)
        self.assertEqual(result["exhaustive_sequences"], 8 * 3**5)
        self.assertEqual(result["failures"], 0)
        self.assertFalse(result["physical_acceptance_replaced"])

    def test_build_is_scoped_deterministic_and_installable_once(self) -> None:
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            output = root / OUTPUT_NAME
            manifest = root / "manifest.json"
            result = build_page_settings_read_only_entry(
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
                after[MENU_LIMIT_OFFSET : MENU_LIMIT_OFFSET + 2], MENU_LIMIT_EIGHT
            )
            self.assertNotEqual(
                before[MENU_DISPATCH_OFFSET : MENU_DISPATCH_OFFSET + 4],
                after[MENU_DISPATCH_OFFSET : MENU_DISPATCH_OFFSET + 4],
            )
            self.assertNotEqual(
                after[
                    SETTINGS_CALLBACK_HIGH_OFFSET : SETTINGS_CALLBACK_HIGH_OFFSET + 4
                ],
                SETTINGS_CALLBACK_HIGH_ORIGINAL,
            )
            self.assertNotEqual(
                after[
                    SETTINGS_CALLBACK_LOW_OFFSET : SETTINGS_CALLBACK_LOW_OFFSET + 4
                ],
                SETTINGS_CALLBACK_LOW_ORIGINAL,
            )
            self.assertEqual(document["payload"]["deterministic_links"], 2)
            self.assertTrue(document["simulation"]["passed"])
            self.assertTrue(document["validation"]["installation_allowed"])
            self.assertEqual(result.sha256, hashlib.sha256(after).hexdigest())
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o444)
            self.assertEqual(stat.S_IMODE(manifest.stat().st_mode), 0o444)

    def test_modified_or_writable_stage_is_rejected_before_build(self) -> None:
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            writable = root / "opt-setting.bin"
            writable.write_bytes(STAGE.read_bytes())
            self.assertEqual(len(writable.read_bytes()), STAGE_SIZE)
            self.assertEqual(hashlib.sha256(writable.read_bytes()).hexdigest(), STAGE_SHA256)
            self.assertEqual(hashlib.md5(writable.read_bytes()).hexdigest(), STAGE_MD5)
            with self.assertRaisesRegex(PageSettingsReadOnlyEntryError, "只读"):
                build_page_settings_read_only_entry(
                    writable,
                    root / OUTPUT_NAME,
                    root / "manifest.json",
                    root / "build",
                    **TOOLS,
                    tool_revision={"commit": "test", "scoped_code_dirty": False},
                )


if __name__ == "__main__":
    unittest.main()
