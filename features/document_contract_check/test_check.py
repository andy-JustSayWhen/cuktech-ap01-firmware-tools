from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from features.document_contract_check import ContractError, check_contract


class ContractCheckTests(unittest.TestCase):
    def _root(self, temporary: str, *, spec: str = "SPEC-A-001") -> Path:
        root = Path(temporary)
        design_directory = root / "reference/DESIGN/ap01-1.0.2_0031-opt.bin技术实现"
        design_directory.mkdir(parents=True)
        (root / "reference/brief.md").write_text("[SPEC](SPEC.md)\n", encoding="utf-8")
        (root / "reference/SPEC.md").write_text(spec + "\n", encoding="utf-8")
        (root / "reference/design.md").write_text(
            "[DESIGN](DESIGN/ap01-1.0.2_0031-opt.bin技术实现/ap01-1.0.2_0031-opt.bin技术实现.md)\n",
            encoding="utf-8",
        )
        (design_directory / "ap01-1.0.2_0031-opt.bin技术实现.md").write_text(
            "最终版设计\n",
            encoding="utf-8",
        )
        return root

    def test_terminal_contract_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = check_contract(self._root(temporary))
            self.assertEqual(report.spec_ids, ("SPEC-A-001",))
            self.assertEqual(report.checked_links, 2)

    def test_missing_clause_stops(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ContractError):
                check_contract(self._root(temporary, spec=""))

    def test_duplicate_clause_stops(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ContractError):
                check_contract(self._root(temporary, spec="SPEC-A-001 SPEC-A-001"))


if __name__ == "__main__":
    unittest.main()
