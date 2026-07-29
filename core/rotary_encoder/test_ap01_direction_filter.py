from __future__ import annotations

import unittest
from pathlib import Path

from core.rotary_encoder import (
    AP01_DIRECTION_FILTER,
    PRESERVED_ENCODER_LOG_RANGES,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_BASELINE = (
    REPO_ROOT / "artifacts/firmware/original/ap01-1.0.2_0031.bin"
)


class AP01DirectionFilterTests(unittest.TestCase):
    def test_contract_matches_reviewed_two_byte_range(self) -> None:
        contract = AP01_DIRECTION_FILTER

        self.assertEqual(contract.offset, 0x108E20)
        self.assertEqual(contract.runtime_address, 0xA0107E20)
        self.assertEqual(contract.return_runtime_address, 0xA0107CBC)
        self.assertEqual(contract.runtime_address, contract.offset + 0x9FFFF000)
        self.assertEqual(contract.expected_before, bytes.fromhex("a14d"))
        self.assertEqual(contract.expected_replacement, bytes.fromhex("71bd"))
        self.assertEqual(len(contract.expected_before), 2)

    @unittest.skipUnless(REAL_BASELINE.is_file(), "真实原厂基线不在本机")
    def test_real_baseline_and_preserved_logs_match_contract(self) -> None:
        original = REAL_BASELINE.read_bytes()
        contract = AP01_DIRECTION_FILTER

        self.assertEqual(
            original[contract.offset : contract.offset + 2],
            contract.expected_before,
        )
        candidate = bytearray(original)
        candidate[contract.offset : contract.offset + 2] = (
            contract.expected_replacement
        )
        for start, end, name in PRESERVED_ENCODER_LOG_RANGES:
            with self.subTest(log=name):
                self.assertFalse(contract.offset < end and start < contract.offset + 2)
                self.assertEqual(candidate[start:end], original[start:end])


if __name__ == "__main__":
    unittest.main()
