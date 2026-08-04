from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from features.web_firmware_flash.operation_store import OperationRecord, OperationStore


class OperationStoreTests(unittest.TestCase):
    def test_atomic_round_trip_contains_only_public_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = OperationStore(Path(temporary))
            record = OperationRecord.create(
                device={"name": "AP01", "model": "njcuk.enstor.ap01", "identity": "masked-01"},
                firmware={"filename": "candidate.bin", "sha256": "a" * 64},
            )
            store.save(record)
            loaded = store.load(record.operation_id)
            self.assertEqual(loaded.to_dict(), record.to_dict())
            raw = next(Path(temporary).glob("*.json")).read_text(encoding="utf-8")
            self.assertNotIn("passToken", raw)
            self.assertEqual(json.loads(raw)["device"]["identity"], "masked-01")

    def test_restart_after_write_becomes_unknown_and_query_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = OperationStore(Path(temporary))
            record = OperationRecord.create(device={}, firmware={})
            record.begin_stage("upload")
            store.save(record)
            recovered = store.recover(record.operation_id)
            self.assertEqual(recovered.status, "unknown")
            self.assertEqual(recovered.allowed_actions, ["query", "export"])

    def test_second_active_operation_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = OperationStore(Path(temporary))
            for _ in range(2):
                store.save(OperationRecord.create(device={}, firmware={}))
            with self.assertRaises(RuntimeError):
                store.active()


if __name__ == "__main__":
    unittest.main()
