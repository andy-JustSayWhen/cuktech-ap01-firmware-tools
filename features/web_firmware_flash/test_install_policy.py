from __future__ import annotations

from dataclasses import replace
import unittest

from features.web_firmware_flash.install_policy import (
    DirectInstallSnapshot,
    decide_direct_install_action,
)


class DirectInstallPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ready = DirectInstallSnapshot(
            operation_started=True,
            device_identity_frozen=True,
            firmware_identity_frozen=True,
            device_online=True,
            device_idle=True,
            simulation_status="passed",
            upload_readback_matches=True,
        )

    def test_simulation_passed_goes_directly_to_single_install(self) -> None:
        decision = decide_direct_install_action(self.ready)

        self.assertEqual(decision.action, "install-once")
        self.assertFalse(decision.ask_user)
        self.assertNotIn("确认", decision.reason)

    def test_simulation_passed_starts_upload_without_confirmation(self) -> None:
        decision = decide_direct_install_action(
            replace(self.ready, upload_readback_matches=None)
        )

        self.assertEqual(decision.action, "upload-and-readback")
        self.assertFalse(decision.ask_user)

    def test_simulation_failure_stops_before_upload_or_install(self) -> None:
        decision = decide_direct_install_action(
            replace(
                self.ready,
                simulation_status="failed",
                upload_readback_matches=None,
            )
        )

        self.assertEqual(decision.action, "stop")
        self.assertFalse(decision.ask_user)

    def test_changed_objective_gate_stops_instead_of_asking(self) -> None:
        cases = (
            replace(self.ready, device_identity_frozen=False),
            replace(self.ready, firmware_identity_frozen=False),
            replace(self.ready, device_online=False),
            replace(self.ready, device_idle=False),
            replace(self.ready, upload_readback_matches=False),
        )

        for snapshot in cases:
            with self.subTest(snapshot=snapshot):
                decision = decide_direct_install_action(snapshot)
                self.assertEqual(decision.action, "stop")
                self.assertFalse(decision.ask_user)

    def test_dispatched_or_unknown_write_is_never_repeated(self) -> None:
        for snapshot in (
            replace(self.ready, install_dispatched=True),
            replace(self.ready, write_state_unknown=True),
        ):
            with self.subTest(snapshot=snapshot):
                decision = decide_direct_install_action(snapshot)
                self.assertEqual(decision.action, "query-only")
                self.assertFalse(decision.ask_user)

    def test_initial_start_is_the_only_user_initiated_boundary(self) -> None:
        decision = decide_direct_install_action(
            replace(
                self.ready,
                operation_started=False,
                simulation_status="pending",
                upload_readback_matches=None,
            )
        )

        self.assertEqual(decision.action, "await-operation-start")
        self.assertFalse(decision.ask_user)


if __name__ == "__main__":
    unittest.main()
