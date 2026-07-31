from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from features.agents_dashboard_firmware.interaction_simulator import (
    InteractionContract,
    InteractionSimulationError,
    InteractionState,
    PageConfiguration,
    run_interaction_simulation,
    simulate_event,
    simulate_manifest,
    write_simulation_report,
)
from features.agents_dashboard_firmware.sync_build import (
    route_stock_local_branch,
)


class InteractionSimulatorTests(unittest.TestCase):
    @staticmethod
    def proven_contract() -> InteractionContract:
        return InteractionContract(
            name="simulator-test-contract",
            local_hook_labels=("萌宠左旋", "萌宠右旋", "萌宠确认"),
            overview_right_target_dispatch=0,
            power_left_enters_agents=True,
            stock_entry_filter_enabled=True,
            power_confirm_isolated=True,
            page_registration_unchanged=True,
            global_key_callback_registration_unchanged=True,
        )

    @staticmethod
    def base_safe_contract() -> InteractionContract:
        return InteractionContract(
            name="FW-AGENTS-010",
            local_hook_labels=(
                "萌宠左旋",
                "萌宠右旋",
                "萌宠确认",
                "共享序号切页过滤",
                "功率确认连接保护",
            ),
            overview_right_target_dispatch=0,
            power_left_enters_agents=True,
            stock_entry_filter_enabled=True,
            power_confirm_isolated=False,
            page_registration_unchanged=True,
            global_key_callback_registration_unchanged=True,
            fixed_shared_pages_enabled=True,
            power_confirm_guard_enabled=True,
            power_confirm_guard_calls_stock_clock=True,
        )

    def test_current_candidate_fails_on_unresolved_final_pages(self) -> None:
        report = run_interaction_simulation(
            InteractionContract.current_stock_resume(),
            route_stock_local_branch,
            exhaustive_depth=4,
        )

        self.assertFalse(report["summary"]["passed"])
        self.assertFalse(report["summary"]["build_allowed"])
        codes = {failure["code"] for failure in report["failures"]}
        self.assertIn("UNRESOLVED_FINAL_PAGE", codes)
        self.assertIn("PRIMARY_PAGE_UNREACHABLE", codes)
        self.assertFalse(
            report["capability_boundary"]["instruction_level_execution"]
        )
        self.assertFalse(
            report["capability_boundary"]["physical_acceptance_replaced"]
        )

    def test_proven_reference_contract_passes_exhaustive_sequences(self) -> None:
        report = run_interaction_simulation(
            self.proven_contract(),
            route_stock_local_branch,
            exhaustive_depth=5,
        )

        self.assertTrue(report["summary"]["passed"])
        self.assertEqual(report["summary"]["failure_count"], 0)
        self.assertEqual(
            report["summary"]["exhaustive_sequence_count"],
            3630,
        )

    def test_base_safe_contract_covers_detached_power_lifecycle(self) -> None:
        report = run_interaction_simulation(
            self.base_safe_contract(),
            route_stock_local_branch,
            exhaustive_depth=5,
        )

        self.assertTrue(report["summary"]["passed"])
        self.assertEqual(
            report["summary"]["exhaustive_sequence_count"],
            4356,
        )
        connected = report["selected_traces"][
            "power-confirm-connected"
        ][-1]
        self.assertEqual(connected["action"], "stock-confirm")
        self.assertEqual(
            connected["after"]["visible_page"],
            "stock-owned:power:confirm",
        )
        for scenario in (
            "power-confirm-detached-stale",
            "power-confirm-data-missing",
        ):
            step = report["selected_traces"][scenario][-1]
            self.assertEqual(step["action"], "power-confirm-guard-to-clock")
            self.assertEqual(step["after"]["visible_page"], "clock")
            self.assertFalse(step["after"]["base_connected"])
            self.assertFalse(step["after"]["power_data_available"])
        for direction in ("left", "right"):
            pages = {
                step["after"]["visible_page"]
                for step in report["selected_traces"][
                    f"detached-primary-cycle:{direction}"
                ]
                if step["after"] is not None
            }
            self.assertNotIn("power", pages)

    def test_detail_and_power_confirm_paths_are_separate(self) -> None:
        contract = self.proven_contract()
        configuration = PageConfiguration()

        detail = simulate_event(
            InteractionState(7, 1),
            "enter",
            configuration,
            contract,
            route_stock_local_branch,
        )
        power = simulate_event(
            InteractionState(0),
            "enter",
            configuration,
            contract,
            route_stock_local_branch,
        )

        self.assertEqual(detail.after.visible_page, "agents-weekly")
        self.assertEqual(power.action, "stock-confirm")
        self.assertEqual(
            power.after.visible_page,
            "stock-owned:power:confirm",
        )

    def test_manifest_contract_uses_actual_hook_and_isolation_gates(self) -> None:
        document = {
            "manifest_type": "agents-local-ui-stock-resume-firmware",
            "validation": {
                "page_filter_switch_call_verified": False,
                "stock_power_confirm_path_unchanged": True,
                "page_registration_unchanged": True,
                "global_key_callback_registration_unchanged": True,
            },
            "callchain_gates": {
                "local_branch_hooks": [
                    {"label": "萌宠左旋"},
                    {"label": "萌宠右旋"},
                    {"label": "萌宠确认"},
                ]
            },
        }
        with tempfile.TemporaryDirectory() as selected:
            manifest = Path(selected) / "manifest.json"
            manifest.write_text(
                json.dumps(document, ensure_ascii=False),
                encoding="utf-8",
            )
            report = simulate_manifest(
                manifest,
                route_stock_local_branch,
                exhaustive_depth=2,
            )

        self.assertFalse(report["summary"]["passed"])
        self.assertIsNotNone(
            report["contract"]["source_manifest_sha256"]
        )

    def test_base_safe_manifest_requires_stock_clock_guard_call(self) -> None:
        document = {
            "manifest_type": "agents-local-ui-base-safe-firmware",
            "validation": {
                "page_filter_switch_call_verified": True,
                "stock_power_confirm_path_unchanged": False,
                "stock_power_confirm_entry_guarded": True,
                "page_registration_unchanged": True,
                "global_key_callback_registration_unchanged": True,
            },
            "callchain_gates": {
                "power_confirm_guard_calls_stock_clock": False,
                "local_branch_hooks": [
                    {"label": "萌宠左旋"},
                    {"label": "萌宠右旋"},
                    {"label": "萌宠确认"},
                    {"label": "共享序号切页过滤"},
                    {"label": "功率确认连接保护"},
                ],
            },
        }
        with tempfile.TemporaryDirectory() as selected:
            manifest = Path(selected) / "manifest.json"
            manifest.write_text(
                json.dumps(document, ensure_ascii=False),
                encoding="utf-8",
            )
            report = simulate_manifest(
                manifest,
                route_stock_local_branch,
                exhaustive_depth=2,
            )

        self.assertFalse(report["summary"]["passed"])
        self.assertIn(
            "POWER_CONFIRM_GUARD_INCOMPLETE",
            {failure["code"] for failure in report["failures"]},
        )

    def test_report_writer_refuses_to_overwrite(self) -> None:
        report = run_interaction_simulation(
            InteractionContract.current_stock_resume(),
            route_stock_local_branch,
            exhaustive_depth=1,
        )
        with tempfile.TemporaryDirectory() as selected:
            target = Path(selected) / "report.json"
            write_simulation_report(target, report)
            saved = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(saved["summary"], report["summary"])
            with self.assertRaisesRegex(
                InteractionSimulationError,
                "拒绝覆盖",
            ):
                write_simulation_report(target, report)


if __name__ == "__main__":
    unittest.main()
