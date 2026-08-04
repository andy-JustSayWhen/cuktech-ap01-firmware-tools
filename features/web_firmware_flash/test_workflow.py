from __future__ import annotations

import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from features.web_firmware_flash.operation_store import OperationStore
from features.web_firmware_flash.workflow import FlashWorkflow, WorkflowError


class _Cloud:
    def __init__(self) -> None:
        self.device = {
            "did": "secret-device",
            "name": "AP01",
            "model": "njcuk.enstor.ap01",
            "fw_version": "1.0.2_0031",
            "isOnline": True,
        }

    def unique_ap01(self):
        return dict(self.device)


def _candidate(root: Path) -> Path:
    path = root / "approved.bin"
    path.write_bytes(b"BFNP" + bytes(6_804_520 - 4))
    payload = path.read_bytes()
    path.with_suffix(".bin.manifest.json").write_text(
        json.dumps(
            {
                "kind": "optimized",
                "model": "njcuk.enstor.ap01",
                "version": "1.0.2_0031",
                "size": len(payload),
                "md5": hashlib.md5(payload).hexdigest(),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "install_approved": True,
            }
        ),
        encoding="utf-8",
    )
    return path


class FlashWorkflowTests(unittest.TestCase):
    def _workflow(self, root: Path, cloud: _Cloud) -> FlashWorkflow:
        return FlashWorkflow(
            release_directory=root,
            store=OperationStore(root / "records"),
            cloud_factory=lambda: cloud,
            simulation=lambda firmware: [f"已绑定 {firmware.sha256}"],
        )

    def _ready(self, root: Path, cloud: _Cloud) -> FlashWorkflow:
        workflow = self._workflow(root, cloud)
        _candidate(root)
        workflow.preflight()
        workflow.identify_device()
        workflow.inspect_firmware("approved.bin")
        workflow.create_operation()
        return workflow

    def test_six_stages_cannot_be_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workflow = self._workflow(root, _Cloud())
            with self.assertRaises(WorkflowError):
                workflow.identify_device()
            workflow.preflight()
            with self.assertRaises(WorkflowError):
                workflow.inspect_firmware("missing.bin")

    def test_full_flow_dispatches_once_and_then_query_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cloud = _Cloud()
            workflow = self._ready(root, cloud)
            operation_id = workflow.operation.operation_id
            with (
                patch("features.web_firmware_flash.workflow.ota_state", return_value={"state": "idle", "progress": 0}),
                patch("features.web_firmware_flash.workflow.upload_and_readback", return_value="https://ota") as upload,
                patch("features.web_firmware_flash.workflow.dispatch_install_once") as dispatch,
            ):
                workflow.start(operation_id)
                workflow._worker.join(timeout=5)
                self.assertFalse(workflow._worker.is_alive())
                self.assertTrue(workflow.operation.install_dispatched)
                self.assertEqual(dispatch.call_count, 1)
                self.assertEqual(upload.call_count, 1)
                workflow.start(operation_id)
                self.assertEqual(dispatch.call_count, 1)

    def test_changed_device_stops_before_upload(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cloud = _Cloud()
            workflow = self._ready(root, cloud)
            cloud.device["did"] = "different"
            with patch("features.web_firmware_flash.workflow.upload_and_readback") as upload:
                workflow.start(workflow.operation.operation_id)
                workflow._worker.join(timeout=5)
                self.assertEqual(upload.call_count, 0)
                self.assertEqual(workflow.operation.status, "stopped")


if __name__ == "__main__":
    unittest.main()
