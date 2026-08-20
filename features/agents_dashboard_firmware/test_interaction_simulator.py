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
    contract_from_manifest,
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

    @staticmethod
    def fixed_hidden_pages_contract() -> InteractionContract:
        return InteractionContract(
            name="FW-PAGE-011",
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
            fixed_hidden_primary_pages_enabled=True,
            calendar_skip_direction_correct=True,
            overview_left_preserves_gif_until_switch=True,
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

    def test_fixed_hidden_pages_never_reach_calendar_or_pet(self) -> None:
        report = run_interaction_simulation(
            self.fixed_hidden_pages_contract(),
            route_stock_local_branch,
            exhaustive_depth=5,
        )

        self.assertTrue(report["summary"]["passed"])
        encoded = json.dumps(report, ensure_ascii=False)
        self.assertNotIn('"visible_page": "calendar"', encoded)
        self.assertNotIn('"visible_page": "pet"', encoded)
        self.assertIn('"visible_page": "agents-overview"', encoded)
        self.assertNotIn('"intermediate_visible_pages": ["pet"]', encoded)

    def test_weather_hidden_pages_jump_to_agents_not_settings(self) -> None:
        current = self.fixed_hidden_pages_contract()
        contract = InteractionContract(
            **{
                **current.__dict__,
                "weather_hidden_primary_page_enabled": True,
            }
        )
        configuration = PageConfiguration(
            calendar_enabled=False,
            pet_enabled=False,
            agents_enabled=True,
        )

        from_clock = simulate_event(
            InteractionState(3),
            "left",
            configuration,
            contract,
            route_stock_local_branch,
        )
        from_weather = simulate_event(
            InteractionState(5),
            "left",
            configuration,
            contract,
            route_stock_local_branch,
        )
        report = run_interaction_simulation(
            contract,
            route_stock_local_branch,
            exhaustive_depth=5,
        )

        self.assertEqual(from_clock.after.visible_page, "agents-overview")
        self.assertEqual(from_weather.after.visible_page, "agents-overview")
        self.assertTrue(report["summary"]["passed"])
        encoded = json.dumps(report, ensure_ascii=False)
        self.assertNotIn('"visible_page": "weather"', encoded)
        self.assertIn('"visible_page": "agents-overview"', encoded)

    def test_rejected_fixed_hidden_mapping_reproduces_device_failures(self) -> None:
        current = self.fixed_hidden_pages_contract()
        contract = InteractionContract(
            **{
                **current.__dict__,
                "name": "FW-PAGE-010",
                "calendar_skip_direction_correct": False,
                "overview_left_preserves_gif_until_switch": False,
            }
        )
        report = run_interaction_simulation(
            contract,
            route_stock_local_branch,
            exhaustive_depth=2,
        )

        self.assertFalse(report["summary"]["passed"])
        codes = {failure["code"] for failure in report["failures"]}
        self.assertIn("CALENDAR_SKIP_DIRECTION_REVERSED", codes)
        self.assertIn("PET_INTERMEDIATE_FRAME_REACHABLE", codes)

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

    def test_live_data_manifest_reuses_base_safe_interaction_contract(self) -> None:
        document = {
            "manifest_type": "agents-live-data-base-safe-firmware",
            "validation": {
                "page_filter_switch_call_verified": True,
                "stock_power_confirm_path_unchanged": False,
                "stock_power_confirm_entry_guarded": True,
                "page_registration_unchanged": True,
                "global_key_callback_registration_unchanged": True,
            },
            "callchain_gates": {
                "power_confirm_guard_calls_stock_clock": True,
                "local_branch_hooks": [
                    {"label": "萌宠左旋"},
                    {"label": "萌宠右旋"},
                    {"label": "萌宠确认"},
                    {"label": "共享序号切页过滤"},
                    {"label": "功率确认连接保护"},
                ],
            },
        }
        contract = contract_from_manifest(document)
        report = run_interaction_simulation(
            contract,
            route_stock_local_branch,
            exhaustive_depth=2,
        )

        self.assertEqual(contract.name, "FW-AGENTS-011")
        self.assertTrue(contract.power_confirm_guard_enabled)
        self.assertTrue(report["summary"]["passed"])

    def test_reference_complete_manifest_uses_fw_agents_012_contract(self) -> None:
        document = {
            "manifest_type": "agents-live-data-reference-complete-firmware",
            "validation": {
                "page_filter_switch_call_verified": True,
                "stock_power_confirm_path_unchanged": False,
                "stock_power_confirm_entry_guarded": True,
                "page_registration_unchanged": True,
                "global_key_callback_registration_unchanged": True,
            },
            "callchain_gates": {
                "power_confirm_guard_calls_stock_clock": True,
                "local_branch_hooks": [
                    {"label": "萌宠左旋"},
                    {"label": "萌宠右旋"},
                    {"label": "萌宠确认"},
                    {"label": "共享序号切页过滤"},
                    {"label": "功率确认连接保护"},
                ],
            },
        }
        contract = contract_from_manifest(document)
        report = run_interaction_simulation(
            contract,
            route_stock_local_branch,
            exhaustive_depth=2,
        )

        self.assertEqual(contract.name, "FW-AGENTS-012")
        self.assertTrue(report["summary"]["passed"])

    def test_low_stack_manifest_uses_fw_agents_013_contract(self) -> None:
        document = {
            "manifest_type": "agents-live-data-low-stack-firmware",
            "validation": {
                "page_filter_switch_call_verified": True,
                "stock_power_confirm_path_unchanged": False,
                "stock_power_confirm_entry_guarded": True,
                "page_registration_unchanged": True,
                "global_key_callback_registration_unchanged": True,
            },
            "callchain_gates": {
                "power_confirm_guard_calls_stock_clock": True,
                "local_branch_hooks": [
                    {"label": "萌宠左旋"},
                    {"label": "萌宠右旋"},
                    {"label": "萌宠确认"},
                    {"label": "共享序号切页过滤"},
                    {"label": "功率确认连接保护"},
                ],
            },
        }
        contract = contract_from_manifest(document)
        report = run_interaction_simulation(
            contract,
            route_stock_local_branch,
            exhaustive_depth=2,
        )

        self.assertEqual(contract.name, "FW-AGENTS-013")
        self.assertTrue(report["summary"]["passed"])

    def test_location_independent_manifest_uses_fw_agents_014_contract(
        self,
    ) -> None:
        document = {
            "manifest_type": "agents-live-data-location-independent-firmware",
            "validation": {
                "page_filter_switch_call_verified": True,
                "stock_power_confirm_path_unchanged": False,
                "stock_power_confirm_entry_guarded": True,
                "page_registration_unchanged": True,
                "global_key_callback_registration_unchanged": True,
            },
            "callchain_gates": {
                "power_confirm_guard_calls_stock_clock": True,
                "local_branch_hooks": [
                    {"label": "萌宠左旋"},
                    {"label": "萌宠右旋"},
                    {"label": "萌宠确认"},
                    {"label": "共享序号切页过滤"},
                    {"label": "功率确认连接保护"},
                ],
            },
        }
        contract = contract_from_manifest(document)
        report = run_interaction_simulation(
            contract,
            route_stock_local_branch,
            exhaustive_depth=2,
        )

        self.assertEqual(contract.name, "FW-AGENTS-014")
        self.assertTrue(report["summary"]["passed"])

    def test_validated_package_manifest_uses_fw_agents_014_contract(
        self,
    ) -> None:
        manifest_types = (
            "agents-live-data-validated-package-firmware",
            "agents-live-data-endpoint-failover-firmware",
        )
        for manifest_type in manifest_types:
            with self.subTest(manifest_type=manifest_type):
                document = {
                    "manifest_type": manifest_type,
                    "validation": {
                        "page_filter_switch_call_verified": True,
                        "stock_power_confirm_path_unchanged": False,
                        "stock_power_confirm_entry_guarded": True,
                        "page_registration_unchanged": True,
                        "global_ui_timer_callback_registration_unchanged": False,
                        "global_key_callback_registration_unchanged": True,
                    },
                    "callchain_gates": {
                        "power_confirm_guard_calls_stock_clock": True,
                        "local_branch_hooks": [
                            {"label": "萌宠左旋"},
                            {"label": "萌宠右旋"},
                            {"label": "萌宠确认"},
                            {"label": "共享序号切页过滤"},
                            {"label": "功率确认连接保护"},
                        ],
                    },
                }
                contract = contract_from_manifest(document)
                report = run_interaction_simulation(
                    contract,
                    route_stock_local_branch,
                    exhaustive_depth=2,
                )

                self.assertEqual(contract.name, "FW-AGENTS-014")
                self.assertTrue(report["summary"]["passed"])

    def test_manifest_simulation_binds_firmware_sha256(self) -> None:
        document = {
            "manifest_type": "agents-live-data-endpoint-failover-firmware",
            "output": {"sha256": "a" * 64},
            "validation": {
                "page_filter_switch_call_verified": True,
                "stock_power_confirm_path_unchanged": False,
                "stock_power_confirm_entry_guarded": True,
                "page_registration_unchanged": True,
                "global_key_callback_registration_unchanged": True,
            },
            "callchain_gates": {
                "power_confirm_guard_calls_stock_clock": True,
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
            manifest.write_text(json.dumps(document), encoding="utf-8")
            report = simulate_manifest(
                manifest,
                route_stock_local_branch,
                exhaustive_depth=2,
            )

        self.assertEqual(report["firmware_sha256"], "a" * 64)
        self.assertTrue(report["summary"]["passed"])

    def test_round_diagnostic_uses_fw_page_011_contract(self) -> None:
        document = {
            "manifest_type": "agents-live-data-round-diagnostic-firmware",
            "validation": {
                "page_filter_switch_call_verified": True,
                "stock_power_confirm_path_unchanged": False,
                "stock_power_confirm_entry_guarded": True,
                "page_registration_unchanged": True,
                "global_key_callback_registration_unchanged": True,
            },
            "callchain_gates": {
                "power_confirm_guard_calls_stock_clock": True,
                "local_branch_hooks": [
                    {"label": "萌宠左旋"},
                    {"label": "萌宠右旋"},
                    {"label": "萌宠确认"},
                    {"label": "共享序号切页过滤"},
                    {"label": "功率确认连接保护"},
                ],
            },
        }
        contract = contract_from_manifest(document)
        self.assertEqual(contract.name, "FW-PAGE-011")
        self.assertTrue(contract.fixed_hidden_primary_pages_enabled)
        document["manifest_type"] = "agents-weather-agents-dual-request-firmware"
        dual_request_contract = contract_from_manifest(document)
        self.assertEqual(dual_request_contract.name, "FW-PAGE-011")
        self.assertTrue(dual_request_contract.fixed_hidden_primary_pages_enabled)
        document["manifest_type"] = "agents-weather-hidden-dashboard-firmware"
        document["transport"] = {"weather_hidden_primary_page": True}
        weather_hidden_contract = contract_from_manifest(document)
        self.assertTrue(weather_hidden_contract.weather_hidden_primary_page_enabled)

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
