from __future__ import annotations

import hashlib
import os
import stat
import struct
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from core.firmware_image import BaselineDefinition, recovery_crc
from features.official_firmware_source.xiaomi_cloud import (
    MODEL,
    OfficialFirmwareError,
    OfficialFirmwareInfo,
    download_latest_official_firmware,
    download_official_firmware,
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
    definition = BaselineDefinition(
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
    return payload, definition


class FakeClient:
    def __init__(self, info: OfficialFirmwareInfo) -> None:
        self.info = info

    def firmware_info(self) -> OfficialFirmwareInfo:
        return self.info


class OfficialFirmwareSourceTests(unittest.TestCase):
    def test_latest_download_uses_cloud_version_for_filename(self) -> None:
        payload = b"new official firmware payload"
        info = OfficialFirmwareInfo(
            model=MODEL,
            version="1.0.2_0032",
            md5=hashlib.md5(payload).hexdigest(),
            change_log="",
            upload_time=None,
            timeout=None,
            url="https://example.test/ap01.bin",
        )
        with tempfile.TemporaryDirectory() as selected:
            with patch(
                "features.official_firmware_source.xiaomi_cloud._download_url",
                return_value=payload,
            ):
                result = download_latest_official_firmware(
                    FakeClient(info), Path(selected)
                )

            self.assertEqual(result.path.name, "ap01-1.0.2_0032.bin")
            self.assertEqual(result.md5, info.md5)
            self.assertEqual(result.size, len(payload))
            self.assertFalse(result.reused_existing)
            self.assertFalse(
                result.path.stat().st_mode
                & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
            )

    def test_latest_download_rejects_unsafe_cloud_version(self) -> None:
        payload = b"payload"
        info = OfficialFirmwareInfo(
            model=MODEL,
            version="../../0032",
            md5=hashlib.md5(payload).hexdigest(),
            change_log="",
            upload_time=None,
            timeout=None,
            url="https://example.test/ap01.bin",
        )
        with tempfile.TemporaryDirectory() as selected:
            with self.assertRaisesRegex(OfficialFirmwareError, "版本"):
                download_latest_official_firmware(FakeClient(info), Path(selected))

    def test_latest_download_rejects_invalid_cloud_md5(self) -> None:
        info = OfficialFirmwareInfo(
            model=MODEL,
            version="1.0.2_0032",
            md5="not-an-md5",
            change_log="",
            upload_time=None,
            timeout=None,
            url="https://example.test/ap01.bin",
        )
        with tempfile.TemporaryDirectory() as selected:
            with self.assertRaisesRegex(OfficialFirmwareError, "32 位"):
                download_latest_official_firmware(FakeClient(info), Path(selected))

    def test_latest_download_rejects_non_https_url(self) -> None:
        payload = b"payload"
        info = OfficialFirmwareInfo(
            model=MODEL,
            version="1.0.2_0032",
            md5=hashlib.md5(payload).hexdigest(),
            change_log="",
            upload_time=None,
            timeout=None,
            url="http://example.test/ap01.bin",
        )
        with tempfile.TemporaryDirectory() as selected:
            with self.assertRaisesRegex(OfficialFirmwareError, "HTTPS"):
                download_latest_official_firmware(FakeClient(info), Path(selected))

    def test_latest_download_rejects_payload_md5_mismatch(self) -> None:
        info = OfficialFirmwareInfo(
            model=MODEL,
            version="1.0.2_0032",
            md5=hashlib.md5(b"expected").hexdigest(),
            change_log="",
            upload_time=None,
            timeout=None,
            url="https://example.test/ap01.bin",
        )
        with tempfile.TemporaryDirectory() as selected:
            with patch(
                "features.official_firmware_source.xiaomi_cloud._download_url",
                return_value=b"different",
            ):
                with self.assertRaisesRegex(OfficialFirmwareError, "MD5"):
                    download_latest_official_firmware(
                        FakeClient(info), Path(selected)
                    )

    def test_latest_download_reuses_matching_read_only_file(self) -> None:
        payload = b"existing official firmware"
        info = OfficialFirmwareInfo(
            model=MODEL,
            version="1.0.2_0032",
            md5=hashlib.md5(payload).hexdigest(),
            change_log="",
            upload_time=None,
            timeout=None,
            url="https://example.test/ap01.bin",
        )
        with tempfile.TemporaryDirectory() as selected:
            target = Path(selected) / "ap01-1.0.2_0032.bin"
            target.write_bytes(payload)
            target.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
            result = download_latest_official_firmware(
                FakeClient(info), Path(selected)
            )
            self.assertTrue(result.reused_existing)
            self.assertEqual(result.sha256, hashlib.sha256(payload).hexdigest())

    def test_latest_download_rejects_writable_existing_file(self) -> None:
        payload = b"existing official firmware"
        info = OfficialFirmwareInfo(
            model=MODEL,
            version="1.0.2_0032",
            md5=hashlib.md5(payload).hexdigest(),
            change_log="",
            upload_time=None,
            timeout=None,
            url="https://example.test/ap01.bin",
        )
        with tempfile.TemporaryDirectory() as selected:
            target = Path(selected) / "ap01-1.0.2_0032.bin"
            target.write_bytes(payload)
            with self.assertRaisesRegex(OfficialFirmwareError, "仍可写"):
                download_latest_official_firmware(
                    FakeClient(info), Path(selected)
                )

    def test_download_validates_cloud_and_freezes_file(self) -> None:
        payload, definition = make_test_baseline()
        info = OfficialFirmwareInfo(
            model=definition.model,
            version=definition.version,
            md5=definition.md5,
            change_log="",
            upload_time=None,
            timeout=None,
            url="https://example.test/ap01.bin",
        )
        with tempfile.TemporaryDirectory() as selected:
            target = Path(selected) / "official.bin"
            with patch(
                "features.official_firmware_source.xiaomi_cloud._download_url",
                return_value=payload,
            ):
                result = download_official_firmware(
                    FakeClient(info), target, definition=definition
                )

            self.assertFalse(result.reused_existing)
            self.assertEqual(result.md5, definition.md5)
            self.assertEqual(result.sha256, definition.sha256)
            self.assertFalse(
                target.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
            )

    def test_download_rejects_name_only_match(self) -> None:
        payload, definition = make_test_baseline()
        wrong = bytearray(payload)
        wrong[64] = 1
        info = OfficialFirmwareInfo(
            model=definition.model,
            version=definition.version,
            md5=definition.md5,
            change_log="",
            upload_time=None,
            timeout=None,
            url="https://example.test/ap01.bin",
        )
        with tempfile.TemporaryDirectory() as selected:
            with patch(
                "features.official_firmware_source.xiaomi_cloud._download_url",
                return_value=bytes(wrong),
            ):
                with self.assertRaisesRegex(OfficialFirmwareError, "MD5"):
                    download_official_firmware(
                        FakeClient(info),
                        Path(selected) / "official.bin",
                        definition=definition,
                    )

    def test_download_stops_when_cloud_version_changes(self) -> None:
        payload, definition = make_test_baseline()
        info = OfficialFirmwareInfo(
            model=definition.model,
            version="2.0.0",
            md5=definition.md5,
            change_log="",
            upload_time=None,
            timeout=None,
            url="https://example.test/ap01.bin",
        )
        with tempfile.TemporaryDirectory() as selected:
            with patch(
                "features.official_firmware_source.xiaomi_cloud._download_url",
                return_value=payload,
            ):
                with self.assertRaisesRegex(OfficialFirmwareError, "云端版本"):
                    download_official_firmware(
                        FakeClient(info),
                        Path(selected) / "official.bin",
                        definition=definition,
                    )

    def test_existing_target_must_be_read_only_and_valid(self) -> None:
        payload, definition = make_test_baseline()
        info = OfficialFirmwareInfo(
            model=definition.model,
            version=definition.version,
            md5=definition.md5,
            change_log="",
            upload_time=None,
            timeout=None,
            url="https://example.test/ap01.bin",
        )
        with tempfile.TemporaryDirectory() as selected:
            target = Path(selected) / "official.bin"
            target.write_bytes(payload)

            with self.assertRaisesRegex(OfficialFirmwareError, "仍可写"):
                download_official_firmware(FakeClient(info), target, definition=definition)

            target.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
            result = download_official_firmware(
                FakeClient(info), target, definition=definition
            )

            self.assertTrue(result.reused_existing)

    def test_reference_model_constant_is_ap01(self) -> None:
        self.assertEqual(MODEL, "njcuk.enstor.ap01")

    def test_cloud_md5_must_match_fixed_baseline(self) -> None:
        payload, definition = make_test_baseline()
        changed_definition = replace(definition, md5="0" * 32)
        info = OfficialFirmwareInfo(
            model=definition.model,
            version=definition.version,
            md5=definition.md5,
            change_log="",
            upload_time=None,
            timeout=None,
            url="https://example.test/ap01.bin",
        )
        with tempfile.TemporaryDirectory() as selected:
            with patch(
                "features.official_firmware_source.xiaomi_cloud._download_url",
                return_value=payload,
            ):
                with self.assertRaisesRegex(OfficialFirmwareError, "云端 MD5"):
                    download_official_firmware(
                        FakeClient(info),
                        Path(selected) / "official.bin",
                        definition=changed_definition,
                    )


if __name__ == "__main__":
    unittest.main()
