import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from features.firmware_installation import select_install_target, install_firmware, FirmwareInstallError
from features.firmware_installation.test_install import FakeCloud, AP01_MODEL


class TargetTests(unittest.TestCase):
    def cloud(self):
        cloud = FakeCloud()
        cloud.devices = lambda: [
            {"did": "old", "model": AP01_MODEL, "isOnline": False},
            {"did": "new", "model": AP01_MODEL, "isOnline": True},
        ]
        return cloud

    def test_user_selection_not_online_selection(self):
        cloud = self.cloud()
        self.assertEqual(select_install_target(cloud, lambda rows: 1)["did"], "old")
        def choose(rows):
            self.assertNotIn("did", rows[0])
            self.assertFalse(rows[0]["online"])
            return 2
        self.assertEqual(select_install_target(cloud, choose)["did"], "new")

    def test_single_auto_and_invalid_choices(self):
        cloud = self.cloud()
        for choice in (0, 3, -1, True, "2"):
            with self.assertRaises(FirmwareInstallError):
                select_install_target(cloud, lambda rows: choice)
        with self.assertRaises(FirmwareInstallError):
            select_install_target(cloud)
        cloud.devices = lambda: [{"did": "only", "model": AP01_MODEL}]
        self.assertEqual(select_install_target(cloud)["did"], "only")
        cloud.devices = lambda: []
        with self.assertRaises(FirmwareInstallError):
            select_install_target(cloud)

    def test_reject_unavailable_targets_without_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            fw = Path(directory) / "test.bin"
            fw.write_bytes(b"BFNPtest")
            for did, state in (("missing", "idle"), ("old", "idle"), ("new", "downloading")):
                cloud = self.cloud()
                with patch("features.firmware_installation.install.query_ap01_update_status",
                           return_value={"state": state, "life": 10}):
                    with self.assertRaises(FirmwareInstallError):
                        install_firmware(cloud, fw, "https://example.test/fw", target_did=did)
                self.assertFalse(cloud.rpc_calls)

    def test_only_selected_target_receives_single_install(self):
        with tempfile.TemporaryDirectory() as directory:
            fw = Path(directory) / "test.bin"
            fw.write_bytes(b"BFNPtest")
            cloud = self.cloud()
            statuses = [
                {"state": "idle", "life": 100, "progress": 101},
                {"state": "downloaded", "life": 100, "progress": 100},
                {"state": "idle", "life": 2, "progress": 101},
            ]
            with patch("features.firmware_installation.install.query_ap01_update_status", side_effect=statuses), patch("features.firmware_installation.install.time.sleep"):
                result = install_firmware(cloud, fw, "https://example.test/fw", target_did="new")
            self.assertTrue(result.reboot_observed)
            self.assertEqual([(d, m) for d, m, p in cloud.rpc_calls], [("new", "miIO.ota")])


if __name__ == "__main__":
    unittest.main()
