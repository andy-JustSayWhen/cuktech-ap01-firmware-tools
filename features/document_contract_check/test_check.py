from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from features.document_contract_check import ContractError, check_contract


class ContractCheckTests(unittest.TestCase):
    def _root(self, temporary: str, *, matrix: str = "SPEC-A-001") -> Path:
        root = Path(temporary)
        (root / "reference/DESIGN").mkdir(parents=True)
        (root / "reference/brief.md").write_text("[SPEC](SPEC.md)\n", encoding="utf-8")
        (root / "reference/SPEC.md").write_text("SPEC-A-001\n", encoding="utf-8")
        (root / "reference/DESIGN/SPEC到DESIGN实现矩阵.md").write_text(matrix, encoding="utf-8")
        return root

    def test_matching_contract_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = check_contract(self._root(temporary))
            self.assertEqual(report.spec_ids, ("SPEC-A-001",))
            self.assertEqual(report.checked_links, 1)

    def test_missing_clause_stops(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ContractError):
                check_contract(self._root(temporary, matrix=""))


if __name__ == "__main__":
    unittest.main()
