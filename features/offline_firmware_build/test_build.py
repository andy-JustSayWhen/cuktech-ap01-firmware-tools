from __future__ import annotations

import json
import hashlib
import os
import struct
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from core.firmware_image import BaselineDefinition, recovery_crc
from features.offline_firmware_build import (
    BuildGateError,
    inspect_baseline,
    load_patch_plan,
    make_firmware,
)


def make_test_baseline() -> tuple[bytes, BaselineDefinition]:
    size = 256
    trailer_offset = size - 40
    recovery_tag = b"0x5245434f56455259544147"
    firmware = bytearray(size)
    firmware[0:4] = b"BFNP"
    firmware[8:12] = b"FCFG"
    firmware[16:20] = b"PCFG"
    model = b"unit.model"
    firmware[40 : 40 + len(model)] = model
    firmware[80 : 80 + len(recovery_tag)] = recovery_tag
    firmware[trailer_offset : trailer_offset + len(recovery_tag)] = recovery_tag
    struct.pack_into(">I", firmware, trailer_offset + 32, size)
    checksum = recovery_crc(firmware[:-4])
    struct.pack_into("<I", firmware, trailer_offset + 36, checksum)
    payload = bytes(firmware)
    return payload, BaselineDefinition(
        model=model.decode("ascii"),
        version="test-version",
        size=size,
        md5=hashlib.md5(payload).hexdigest(),
        sha256=hashlib.sha256(payload).hexdigest(),
        header_markers=((0, b"BFNP"), (8, b"FCFG"), (16, b"PCFG")),
        model_offsets=(40,),
        recovery_tag=recovery_tag,
        recovery_tag_offsets=(80, trailer_offset),
        recovery_trailer_offset=trailer_offset,
        recovery_crc_value=checksum,
        immutable_header_end=32,
    )


class OfflineFirmwareBuildTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        (self.repo / "knowledge").mkdir()
        (self.repo / "knowledge" / "evidence.md").write_text(
            "# 直接证据\n",
            encoding="utf-8",
        )
        self.source = self.root / "original.bin"
        self.baseline, self.definition = make_test_baseline()
        self.source.write_bytes(self.baseline)
        self.source.chmod(0o444)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_plan(self, patches: list[dict[str, object]]) -> Path:
        plan = {
            "schema_version": 1,
            "status": "approved-for-offline-build",
            "target": {
                "model": self.definition.model,
                "version": self.definition.version,
                "baseline_sha256": self.definition.sha256,
            },
            "patches": patches,
        }
        path = self.repo / "plan.json"
        path.write_text(
            json.dumps(plan, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def valid_patch(self) -> dict[str, object]:
        return {
            "name": "测试修改",
            "objective": "证明旧字节断言与构建清单工作正常",
            "offset": 64,
            "expected_before_hex": "0000",
            "replacement_hex": "0102",
            "evidence_path": "knowledge/evidence.md",
            "evidence_note": "测试基线中的已知空闲字节",
            "region_kind": "application-code",
        }

    def cloud_checked_at(self) -> str:
        return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")

    def test_inspection_writes_report_without_firmware_output(self) -> None:
        report = self.repo / "artifacts" / "baseline.json"

        document = inspect_baseline(
            self.source,
            report,
            tool_revision={"commit": "test", "scoped_code_dirty": False},
            cloud_version=self.definition.version,
            cloud_md5=self.definition.md5,
            cloud_checked_at=self.cloud_checked_at(),
            definition=self.definition,
        )

        self.assertTrue(report.is_file())
        self.assertFalse(document["gates"]["offline_build_allowed"])
        self.assertEqual(
            list((self.repo / "artifacts").glob("*.bin")),
            [],
        )

    def test_empty_patch_plan_is_rejected(self) -> None:
        plan = self.write_plan([])

        with self.assertRaisesRegex(BuildGateError, "伪装成优化固件"):
            load_patch_plan(plan, self.repo, self.definition)

    def test_build_applies_asserted_patch_and_freezes_outputs(self) -> None:
        plan = self.write_plan([self.valid_patch()])
        output = self.repo / "artifacts" / "opt-setting.bin"
        manifest = self.repo / "artifacts" / "build-manifest.json"

        result = make_firmware(
            self.source,
            plan,
            output,
            manifest,
            repo_root=self.repo,
            tool_revision={"commit": "test", "scoped_code_dirty": False},
            cloud_version=self.definition.version,
            cloud_md5=self.definition.md5,
            cloud_checked_at=self.cloud_checked_at(),
            definition=self.definition,
        )

        self.assertEqual(result.output, output.resolve())
        self.assertEqual(output.read_bytes()[64:66], b"\x01\x02")
        self.assertEqual(os.stat(output).st_mode & 0o222, 0)
        self.assertEqual(os.stat(manifest).st_mode & 0o222, 0)
        document = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertFalse(document["validation"]["installation_allowed"])
        self.assertTrue(document["validation"]["frozen_readback_sha256_matches"])

    def test_settings_stage_rejects_final_firmware_name(self) -> None:
        plan = self.write_plan([self.valid_patch()])
        output = self.repo / "artifacts" / "ap01-1.0.2_0031-opt.bin"
        manifest = self.repo / "artifacts" / "build-manifest.json"

        with self.assertRaisesRegex(BuildGateError, "opt-setting.bin"):
            make_firmware(
                self.source,
                plan,
                output,
                manifest,
                repo_root=self.repo,
                tool_revision={"commit": "test", "scoped_code_dirty": False},
                cloud_version=self.definition.version,
                cloud_md5=self.definition.md5,
                cloud_checked_at=self.cloud_checked_at(),
                definition=self.definition,
            )

        self.assertFalse(output.exists())
        self.assertFalse(manifest.exists())

    def test_wrong_old_bytes_stop_before_output(self) -> None:
        patch = self.valid_patch()
        patch["expected_before_hex"] = "ffff"
        plan = self.write_plan([patch])
        output = self.repo / "artifacts" / "opt-setting.bin"
        manifest = self.repo / "artifacts" / "build-manifest.json"

        with self.assertRaisesRegex(BuildGateError, "旧字节断言失败"):
            make_firmware(
                self.source,
                plan,
                output,
                manifest,
                repo_root=self.repo,
                tool_revision={"commit": "test", "scoped_code_dirty": False},
                cloud_version=self.definition.version,
                cloud_md5=self.definition.md5,
                cloud_checked_at=self.cloud_checked_at(),
                definition=self.definition,
            )

        self.assertFalse(output.exists())
        self.assertFalse(manifest.exists())


if __name__ == "__main__":
    unittest.main()
