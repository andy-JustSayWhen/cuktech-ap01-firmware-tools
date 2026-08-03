from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from features.primary_page_settings.constructor_label import (
    LABEL_CONSTRUCTOR_CALL_OFFSET,
    OUTPUT_NAME,
    STARTUP_LIST_CALL_OFFSET,
    STARTUP_LIST_CALL_ORIGINAL,
    USER_LIST_CALL_OFFSET,
    USER_LIST_CALL_ORIGINAL,
    build_page_settings_constructor_label,
    simulate_page_settings_constructor_label,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
STAGE = REPO_ROOT / "artifacts/firmware/ap01-1.0.2_0031-page-settings-startup-passthrough.bin"


def _tool(name: str) -> Path:
    return Path(shutil.which(name) or f"/opt/homebrew/bin/{name}")


TOOLS = {
    "assembler": _tool("riscv64-elf-as"),
    "linker": _tool("riscv64-elf-ld"),
    "copier": _tool("riscv64-elf-objcopy"),
    "readelf": _tool("riscv64-elf-readelf"),
    "nm": _tool("riscv64-elf-nm"),
    "dumper": _tool("riscv64-elf-objdump"),
}


class PageSettingsConstructorLabelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not STAGE.is_file() or not all(item.is_file() for item in TOOLS.values()):
            raise unittest.SkipTest("本机缺少 A 阶段输入或设备端构建工具")

    def test_simulation_is_stateless_and_selects_only_user_caller(self) -> None:
        result = simulate_page_settings_constructor_label()
        self.assertTrue(result["passed"])
        self.assertFalse(result["mutable_state"])
        self.assertFalse(result["object_traversal"])
        self.assertEqual(result["static_stack_bytes"], 0)
        labels = [item["label"] for item in result["scenarios"]]
        self.assertEqual(labels, ["返回", "开关一级页面", "开关一级页面", "返回"])

    def test_build_keeps_both_list_calls_and_uses_one_hook(self) -> None:
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            output = root / OUTPUT_NAME
            manifest = root / "manifest.json"
            build_page_settings_constructor_label(
                STAGE,
                output,
                manifest,
                root / "build",
                **TOOLS,
                tool_revision={"commit": "test", "scoped_code_dirty": False},
            )
            before = STAGE.read_bytes()
            after = output.read_bytes()
            self.assertEqual(
                after[STARTUP_LIST_CALL_OFFSET : STARTUP_LIST_CALL_OFFSET + 4],
                STARTUP_LIST_CALL_ORIGINAL,
            )
            self.assertEqual(
                after[USER_LIST_CALL_OFFSET : USER_LIST_CALL_OFFSET + 4],
                USER_LIST_CALL_ORIGINAL,
            )
            self.assertNotEqual(
                after[LABEL_CONSTRUCTOR_CALL_OFFSET : LABEL_CONSTRUCTOR_CALL_OFFSET + 4],
                before[LABEL_CONSTRUCTOR_CALL_OFFSET : LABEL_CONSTRUCTOR_CALL_OFFSET + 4],
            )
            document = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertTrue(document["validation"]["static_stack_zero"])
            self.assertTrue(document["validation"]["mutable_state_absent"])
            self.assertFalse(document["validation"]["installation_allowed"])


if __name__ == "__main__":
    unittest.main()
