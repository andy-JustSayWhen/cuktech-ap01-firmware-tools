from __future__ import annotations

import json
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from core.firmware_image import changed_ranges
from features.primary_page_settings.hook_observation import (
    HOOK_OFFSET,
    MENU_LIMIT_OFFSET,
    MENU_LIMIT_ORIGINAL,
    OUTPUT_NAME,
    SETTINGS_CALLBACK_HIGH_OFFSET,
    SETTINGS_CALLBACK_HIGH_ORIGINAL,
    SETTINGS_CALLBACK_LOW_OFFSET,
    SETTINGS_CALLBACK_LOW_ORIGINAL,
    SettingsHookObservationError,
    build_settings_hook_observation,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
STAGE = REPO_ROOT / "artifacts/firmware/ap01-1.0.2_0031-agents-sync-experimental.bin"


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
}


class SettingsHookObservationTests(unittest.TestCase):
    def setUp(self) -> None:
        if not STAGE.is_file() or not all(item.is_file() for item in TOOLS.values()):
            self.skipTest("本机缺少已验收同步固件或设备端构建工具")

    def test_build_changes_only_hook_payload_and_recovery_crc(self) -> None:
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            output = root / OUTPUT_NAME
            manifest = root / "manifest.json"
            result = build_settings_hook_observation(
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
                        start <= difference.start
                        and difference.end <= end
                        for start, end in allowed
                    )
                )
            self.assertEqual(
                after[MENU_LIMIT_OFFSET : MENU_LIMIT_OFFSET + 2],
                MENU_LIMIT_ORIGINAL,
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
            self.assertNotEqual(
                before[HOOK_OFFSET : HOOK_OFFSET + 4],
                after[HOOK_OFFSET : HOOK_OFFSET + 4],
            )
            self.assertEqual(result.payload_size, 32_056 + document["payload"]["size"])
            self.assertFalse(document["validation"]["installation_allowed"])
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o444)
            self.assertEqual(stat.S_IMODE(manifest.stat().st_mode), 0o444)

    def test_payload_disassembly_returns_to_both_original_branches(self) -> None:
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            manifest = root / "manifest.json"
            build_settings_hook_observation(
                STAGE,
                root / OUTPUT_NAME,
                manifest,
                root / "build",
                **TOOLS,
                tool_revision={"commit": "test", "scoped_code_dirty": False},
            )
            elf = Path(
                json.loads(manifest.read_text(encoding="utf-8"))["payload"]["elf"]
            )
            completed = subprocess.run(
                [
                    str(_tool("riscv64-elf-objdump")),
                    "-d",
                    "-M",
                    "no-aliases",
                    str(elf),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("a01989e0", completed.stdout.lower())
            self.assertIn("a0198ad0", completed.stdout.lower())
            self.assertNotIn("a0192fb4", completed.stdout.lower())

    def test_modified_stage_is_rejected_before_build(self) -> None:
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            modified = root / "stage.bin"
            payload = bytearray(STAGE.read_bytes())
            payload[0x2000] ^= 1
            modified.write_bytes(payload)
            modified.chmod(0o444)
            with self.assertRaisesRegex(
                SettingsHookObservationError,
                "SHA-256",
            ):
                build_settings_hook_observation(
                    modified,
                    root / OUTPUT_NAME,
                    root / "manifest.json",
                    root / "build",
                    **TOOLS,
                    tool_revision={"commit": "test", "scoped_code_dirty": False},
                )


if __name__ == "__main__":
    unittest.main()
