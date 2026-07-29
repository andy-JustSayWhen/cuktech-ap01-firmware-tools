from __future__ import annotations

import hashlib
import stat
import struct
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from core.firmware_image import (
    BaselineDefinition,
    ByteRange,
    FirmwareValidationError,
    changed_ranges,
    prepare_read_only_copy,
    recovery_crc,
    refresh_recovery_crc,
    validate_baseline,
    validate_candidate,
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


class FirmwareImageTests(unittest.TestCase):
    def test_exact_baseline_is_accepted(self) -> None:
        firmware, definition = make_test_baseline()

        report = validate_baseline(firmware, definition)

        self.assertEqual(report.model, "unit.model")
        self.assertEqual(report.recovery.stored_crc, definition.recovery_crc_value)

    def test_baseline_rejects_changed_byte(self) -> None:
        firmware, definition = make_test_baseline()
        changed = bytearray(firmware)
        changed[64] = 1

        with self.assertRaisesRegex(FirmwareValidationError, "MD5"):
            validate_baseline(bytes(changed), definition)

    def test_candidate_requires_every_changed_byte_to_be_declared(self) -> None:
        baseline, definition = make_test_baseline()
        candidate = bytearray(baseline)
        candidate[64:66] = b"\x01\x02"
        candidate[70] = 3
        refresh_recovery_crc(candidate, definition)
        checksum_range = ByteRange(
            definition.recovery_trailer_offset + 36,
            definition.recovery_trailer_offset + 40,
        )

        with self.assertRaisesRegex(FirmwareValidationError, "允许范围外"):
            validate_candidate(
                baseline,
                bytes(candidate),
                (ByteRange(64, 66), checksum_range),
                definition,
            )

    def test_candidate_preserves_header_and_reports_ranges(self) -> None:
        baseline, definition = make_test_baseline()
        candidate = bytearray(baseline)
        candidate[64:66] = b"\x01\x02"
        refresh_recovery_crc(candidate, definition)
        checksum_range = ByteRange(
            definition.recovery_trailer_offset + 36,
            definition.recovery_trailer_offset + 40,
        )

        report = validate_candidate(
            baseline,
            bytes(candidate),
            (ByteRange(64, 66), checksum_range),
            definition,
        )

        self.assertTrue(report.immutable_header_identical)
        self.assertTrue(report.outside_allowed_ranges_identical)
        self.assertEqual(report.recovery.stored_crc, report.recovery.calculated_crc)
        self.assertEqual(changed_ranges(baseline, bytes(candidate)), report.changed_ranges)

    def test_baseline_definition_fingerprint_is_not_inferred(self) -> None:
        firmware, definition = make_test_baseline()
        wrong = replace(definition, sha256="0" * 64)

        with self.assertRaisesRegex(FirmwareValidationError, "SHA-256"):
            validate_baseline(firmware, wrong)

    def test_prepare_read_only_copy_verifies_and_freezes_material(self) -> None:
        payload = b"firmware-material"
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            source = root / "source.bin"
            source.write_bytes(payload)

            prepared = prepare_read_only_copy(
                source,
                root / "private",
                expected_size=len(payload),
                expected_sha256=hashlib.sha256(payload).hexdigest(),
                expected_md5=hashlib.md5(payload).hexdigest(),
            )

            self.assertEqual(prepared.path.read_bytes(), payload)
            self.assertFalse(
                prepared.path.stat().st_mode
                & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
            )
            self.assertFalse(prepared.reused)

    def test_prepare_read_only_copy_rejects_wrong_fingerprint(self) -> None:
        payload = b"firmware-material"
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            source = root / "source.bin"
            source.write_bytes(payload)

            with self.assertRaisesRegex(FirmwareValidationError, "SHA-256"):
                prepare_read_only_copy(
                    source,
                    root / "private",
                    expected_size=len(payload),
                    expected_sha256="0" * 64,
                )

    def test_prepare_read_only_copy_does_not_overwrite_unknown_target(self) -> None:
        payload = b"firmware-material"
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            source = root / "source.bin"
            source.write_bytes(payload)
            target_directory = root / "private"
            target_directory.mkdir()
            target = target_directory / source.name
            target.write_bytes(b"unknown")

            with self.assertRaisesRegex(FirmwareValidationError, "字节数"):
                prepare_read_only_copy(
                    source,
                    target_directory,
                    expected_size=len(payload),
                    expected_sha256=hashlib.sha256(payload).hexdigest(),
                )
            self.assertEqual(target.read_bytes(), b"unknown")

    def test_prepare_read_only_copy_rejects_matching_writable_target(self) -> None:
        payload = b"firmware-material"
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            source = root / "source.bin"
            source.write_bytes(payload)
            target_directory = root / "private"
            target_directory.mkdir()
            target = target_directory / source.name
            target.write_bytes(payload)

            with self.assertRaisesRegex(FirmwareValidationError, "仍可写"):
                prepare_read_only_copy(
                    source,
                    target_directory,
                    expected_size=len(payload),
                    expected_sha256=hashlib.sha256(payload).hexdigest(),
                )

    def test_prepare_read_only_copy_reuses_matching_read_only_target(self) -> None:
        payload = b"firmware-material"
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            source = root / "source.bin"
            source.write_bytes(payload)
            target_directory = root / "private"
            target_directory.mkdir()
            target = target_directory / source.name
            target.write_bytes(payload)
            target.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)

            prepared = prepare_read_only_copy(
                source,
                target_directory,
                expected_size=len(payload),
                expected_sha256=hashlib.sha256(payload).hexdigest(),
            )

            self.assertTrue(prepared.reused)
            self.assertEqual(prepared.path, target.resolve())


if __name__ == "__main__":
    unittest.main()
