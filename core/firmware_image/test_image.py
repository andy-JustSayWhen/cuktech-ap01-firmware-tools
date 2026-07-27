from __future__ import annotations

import hashlib
import struct
import unittest
from dataclasses import replace

from core.firmware_image import (
    BaselineDefinition,
    ByteRange,
    FirmwareValidationError,
    changed_ranges,
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


if __name__ == "__main__":
    unittest.main()
