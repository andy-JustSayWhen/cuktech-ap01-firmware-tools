from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest import mock

from core.firmware_image import prepare_read_only_copy
from features.agents_dashboard.result_package import encode_package
from features.agents_dashboard_firmware import (
    build_observation_firmware,
    build_page_registration_payload,
)
from features.agents_dashboard_firmware.build import OBSERVATION_OUTPUT_FILENAME
from features.agents_dashboard_firmware.build import (
    HOOK_OFFSET,
    HOOK_ORIGINAL,
    KEY_CALLBACK_HIGH_OFFSET,
    KEY_CALLBACK_HIGH_ORIGINAL,
    KEY_CALLBACK_LOW_OFFSET,
    KEY_CALLBACK_LOW_ORIGINAL,
    TRAMPOLINE_OFFSET,
    TRAMPOLINE_ORIGINAL,
    STAGE_SHA256,
    STAGE_SIZE,
    _absolute_tail_jump,
    _encode_jal,
)
from features.agents_dashboard_firmware.sync_build import (
    AgentsDashboardFirmwareError,
    INSTRUCTION_EXPECTED,
    FAILURE_BACKOFF_STORE,
    HTTP_PERFORM_CALL,
    HTTPS_PERFORM_CALL,
    LOCATION_LOOKUP_CALL,
    LOCATION_TRAMPOLINE_OFFSET,
    LOCATION_TRAMPOLINE_ORIGINAL,
    LOADER_SOURCE,
    LOADER_TRAMPOLINE_OFFSET,
    LOADER_TRAMPOLINE_ORIGINAL,
    POST_WEATHER_FETCH_HOOK,
    POST_WEATHER_FETCH_HOOK_ORIGINAL,
    POST_WEATHER_FETCH_TRAMPOLINE_OFFSET,
    POST_WEATHER_FETCH_TRAMPOLINE_ORIGINAL,
    URL_REGIONS,
    LIVE_DATA_BASE_SAFE_OUTPUT_FILENAME,
    LIVE_DATA_REFERENCE_COMPLETE_OUTPUT_FILENAME,
    LIVE_DATA_LOW_STACK_OUTPUT_FILENAME,
    LIVE_DATA_ENDPOINT_FAILOVER_OUTPUT_FILENAME,
    LIVE_DATA_FIXED_PRIMARY_PAGES_OUTPUT_FILENAME,
    LIVE_DATA_WEATHER_COEXISTENCE_OUTPUT_FILENAME,
    LIVE_DATA_WEATHER_ROUND_ROBIN_OUTPUT_FILENAME,
    LIVE_DATA_ROUND_DIAGNOSTIC_OUTPUT_FILENAME,
    LIVE_DATA_DOWNLOAD_DIAGNOSTIC_OUTPUT_FILENAME,
    LIVE_DATA_RESULT_DIAGNOSTIC_OUTPUT_FILENAME,
    LIVE_DATA_PUBLISH_DIAGNOSTIC_OUTPUT_FILENAME,
    LIVE_DATA_ADOPTION_DIAGNOSTIC_OUTPUT_FILENAME,
    LIVE_DATA_STABLE_ADOPTION_OUTPUT_FILENAME,
    LIVE_DATA_WEATHER_AGENTS_DUAL_REQUEST_OUTPUT_FILENAME,
    LIVE_DATA_STOCK_HTTPS_DUAL_REQUEST_OUTPUT_FILENAME,
    LIVE_DATA_WEATHER_PRESERVED_DUAL_REQUEST_OUTPUT_FILENAME,
    LIVE_DATA_WEATHER_STOCK_FIRST_DUAL_REQUEST_OUTPUT_FILENAME,
    LIVE_DATA_WEATHER_HIDDEN_DASHBOARD_OUTPUT_FILENAME,
    LIVE_DATA_WEATHER_HIDDEN_DASHBOARD_V2_OUTPUT_FILENAME,
    PUBLIC_FIRMWARE_OUTPUT_FILENAME,
    PERSONALIZED_FIRMWARE_OUTPUT_FILENAME,
    LIVE_DATA_WEATHER_SOLO_REQUEST_OUTPUT_FILENAME,
    LIVE_DATA_STOCK_HTTPS_UNTOUCHED_OUTPUT_FILENAME,
    LIVE_DATA_POST_WEATHER_FETCH_OUTPUT_FILENAME,
    LIVE_DATA_LOCATION_SLOT_DASHBOARD_OUTPUT_FILENAME,
    LIVE_DATA_LOCATION_INDEPENDENT_OUTPUT_FILENAME,
    LIVE_DATA_VALIDATED_PACKAGE_OUTPUT_FILENAME,
    LOCAL_UI_FORBIDDEN_CALLEES,
    LOCAL_UI_FORBIDDEN_SYMBOLS,
    LOCAL_UI_BASE_SAFE_OUTPUT_FILENAME,
    LOCAL_UI_POWER_CONFIRM_GUARD_HOOK,
    LOCAL_UI_POWER_SAFE_OUTPUT_FILENAME,
    LOCAL_UI_SHARED_PAGE_FILTER_HOOK,
    LOCAL_UI_STOCK_SAFE_OUTPUT_FILENAME,
    LOCAL_UI_STOCK_RESUME_OUTPUT_FILENAME,
    LOW_STACK_LOCAL_BRANCHES_OUTPUT_FILENAME,
    OPT_REWRITE_OUTPUT_FILENAME,
    PET_STATE_SIZE_EXTENDED,
    PET_STATE_SIZE_OFFSET,
    PET_STATE_SIZE_ORIGINAL,
    SINK_CALLBACK_ADDI,
    SINK_CALLBACK_LUI,
    STOCK_CALLCHAIN_OUTPUT_FILENAME,
    STOCK_ENTER_GATE_OUTPUT_FILENAME,
    STOCK_KEY_CALLBACK_RANGE,
    STOCK_LOCAL_BRANCH_HOOKS,
    STOCK_POWER_CONFIRM_RANGE,
    SUCCESS_TIMER_ADD,
    SUCCESS_TIMER_ADDI,
    SUCCESS_TIMER_BASE_ADDI,
    SUCCESS_TIMER_LUI,
    SUCCESS_TIMER_REM,
    UI_CALLBACK_ADDI,
    UI_CALLBACK_LUI,
    URL_REGIONS,
    XIP_DELTA,
    _request_formats,
    build_stock_callchain_firmware,
    build_stock_enter_gate_firmware,
    build_local_ui_power_safe_firmware,
    build_local_ui_base_safe_firmware,
    build_local_ui_stock_safe_firmware,
    build_local_ui_stock_resume_firmware,
    build_low_stack_local_branches_firmware,
    build_live_data_base_safe_firmware,
    build_live_data_reference_complete_firmware,
    build_live_data_low_stack_firmware,
    build_live_data_endpoint_failover_firmware,
    build_live_data_fixed_primary_pages_firmware,
    build_live_data_weather_coexistence_firmware,
    build_live_data_weather_round_robin_firmware,
    build_live_data_round_diagnostic_firmware,
    build_live_data_download_diagnostic_firmware,
    build_live_data_result_diagnostic_firmware,
    build_live_data_publish_diagnostic_firmware,
    build_live_data_adoption_diagnostic_firmware,
    build_live_data_stable_adoption_firmware,
    build_live_data_weather_agents_dual_request_firmware,
    build_live_data_stock_https_dual_request_firmware,
    build_live_data_weather_preserved_dual_request_firmware,
    build_live_data_weather_stock_first_dual_request_firmware,
    build_live_data_weather_hidden_dashboard_firmware,
    build_live_data_weather_hidden_dashboard_v2_firmware,
    build_live_data_weather_solo_request_firmware,
    build_live_data_stock_https_untouched_firmware,
    build_live_data_post_weather_fetch_firmware,
    build_live_data_location_slot_dashboard_firmware,
    build_live_data_location_independent_firmware,
    build_live_data_validated_package_firmware,
    build_sync_firmware,
    build_sync_payload,
    decode_agents_state,
    encode_agents_state,
    route_stock_local_branch,
    validate_stock_local_branch_routes,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
STAGE = REPO_ROOT / "artifacts/firmware/ap01-1.0.2_0031-opt-setting.bin"


def _test_gif(frame_count: int = 2, *, embedded_marker: bool = False) -> bytes:
    header = b"GIF89a\x40\x01\xf0\x00\x80\x00\x00"
    color_table = b"\x00\x00\x00\xff\xff\xff"
    compressed = b"\x2c\x01" if embedded_marker else b"\x44\x01"
    frame = (
        b"\x2c"
        b"\x00\x00\x00\x00\x01\x00\x01\x00\x00"
        b"\x02\x02"
        + compressed
        + b"\x00"
    )
    return header + color_table + frame * frame_count + b"\x3b"


class AgentsDashboardFirmwareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not STAGE.is_file():
            raise unittest.SkipTest("本机没有阶段固件")
        cls._material_directory = tempfile.TemporaryDirectory()
        cls.stage = prepare_read_only_copy(
            STAGE,
            Path(cls._material_directory.name),
            expected_size=STAGE_SIZE,
            expected_sha256=STAGE_SHA256,
        ).path

    @classmethod
    def tearDownClass(cls) -> None:
        cls._material_directory.cleanup()

    def test_real_stage_builds_linked_page_registration_payload(self) -> None:
        if not shutil.which("riscv64-elf-as"):
            self.skipTest("本机没有阶段固件或固定编译工具")
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            document = build_page_registration_payload(
                self.stage,
                root / "build",
                root / "report.json",
                tool_revision={"commit": "test", "scoped_code_dirty": False},
            )

        self.assertEqual(document["payload"]["relocations"], 0)
        self.assertTrue(document["gates"]["payload_fits"])
        self.assertTrue(document["gates"]["required_callees_present"])
        self.assertTrue(document["gates"]["fallback_descriptors_valid"])
        self.assertTrue(document["gates"]["key_callback_old_bytes_match"])
        self.assertTrue(document["gates"]["key_event_entry_present"])
        self.assertTrue(document["gates"]["current_index_getter_present"])
        self.assertTrue(document["gates"]["dynamic_primary_count_present"])
        self.assertTrue(document["gates"]["initial_x_call_present"])
        self.assertFalse(document["gates"]["firmware_output_allowed"])
        self.assertEqual(
            document["primary_navigation"]["normal_sequence"],
            [0, 3, 4, 5, 6, 7, 8],
        )
        self.assertEqual(
            document["primary_navigation"]["stock_conditional_port_indices"],
            [1, 2],
        )
        self.assertEqual(
            document["primary_navigation"]["stock_mijia_detail_index"],
            9,
        )
        self.assertEqual(document["payload"]["size"], 27_688)
        self.assertEqual(document["payload"]["remaining"], 33_246)
        self.assertEqual(len(document["fallback_assets"]), 4)
        self.assertEqual(
            document["draft_modifications"][0]["expected_before_hex"],
            "2ae30500",
        )
        self.assertEqual(
            document["draft_modifications"][2]["expected_before_hex"],
            "5285eff02079",
        )
        self.assertEqual(
            document["draft_modifications"][4]["expected_before_hex"],
            "b7c50ba0",
        )
        self.assertEqual(
            document["draft_modifications"][5]["expected_before_hex"],
            "9385e5fe",
        )

    def test_changed_page_payload_cannot_reuse_observation_approval(self) -> None:
        if not shutil.which("riscv64-elf-as"):
            self.skipTest("本机没有阶段固件或固定编译工具")
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            output = root / OBSERVATION_OUTPUT_FILENAME
            manifest = root / "manifest.json"
            with self.assertRaisesRegex(
                RuntimeError,
                "真机观察批准记录字段不匹配：output_sha256",
            ):
                build_observation_firmware(
                    self.stage,
                    output,
                    manifest,
                    root / "build",
                    tool_revision={"commit": "test", "scoped_code_dirty": False},
                )

    def test_local_ui_stock_resume_payload_is_bounded_and_isolated(self) -> None:
        if (
            not shutil.which("riscv64-elf-as")
            or not shutil.which("riscv64-elf-gcc")
        ):
            self.skipTest("本机没有阶段固件或固定编译工具")
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            payload = build_sync_payload(
                self.stage,
                root / "payload",
                tool_revision={"commit": "test", "scoped_code_dirty": False},
                reuse_stock_pet=True,
                local_ui_only=True,
            )
            disassembly = subprocess.run(
                ["riscv64-elf-objdump", "-d", payload.elf],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            output = root / LOCAL_UI_STOCK_RESUME_OUTPUT_FILENAME
            manifest = root / "manifest.json"
            proven_simulation = {
                "summary": {"passed": True, "build_allowed": True},
                "failures": [],
                "selected_traces": {},
            }
            with mock.patch(
                "features.agents_dashboard_firmware.interaction_simulator."
                "run_interaction_simulation",
                return_value=proven_simulation,
            ):
                result = build_local_ui_stock_resume_firmware(
                    self.stage,
                    output,
                    manifest,
                    root / "firmware",
                    tool_revision={
                        "commit": "test",
                        "scoped_code_dirty": False,
                    },
                )
            manifest_text = manifest.read_text(encoding="utf-8")
            manifest_document = json.loads(manifest_text)
            output_bytes = output.read_bytes()
            payload_bytes = payload.binary.read_bytes()

        self.assertLess(payload.size, 60_934)
        self.assertGreater(60_934 - payload.size, 20_000)
        self.assertLessEqual(payload.maximum_static_stack, 320)
        self.assertEqual(result.payload_size, payload.size)
        self.assertEqual(len(output_bytes), self.stage.stat().st_size)
        self.assertTrue(output_bytes.startswith(b"BFNP"))
        self.assertIn('"installation_allowed": false', manifest_text)
        self.assertEqual(
            manifest_document["manifest_type"],
            "agents-local-ui-stock-resume-firmware",
        )
        self.assertFalse(manifest_document["transport"]["enabled"])
        self.assertFalse(manifest_document["device_specific"])
        self.assertTrue(
            manifest_document["interaction_simulation"]["summary"]["passed"]
        )
        self.assertTrue(manifest_document["payload"]["local_ui_only"])
        self.assertFalse(
            manifest_document["payload"]["transport_symbols_linked"]
        )
        self.assertIn('"stock_pet_object_reused": true', manifest_text)
        self.assertEqual(
            payload.route_validation,
            {
                "local_branch_state_cases": 15,
                "detail_rotation_cases": 6,
                "disabled_page_cases": 2,
                "invalid_tail_cases": 5,
                "valid_tail_cases": 5,
                "switch_failure_recovery_cases": 1,
                "overview_right_stock_resume_cases": 1,
                "gif_failure_recovery_cases": 2,
                "lifecycle_recovery_cases": 2,
            },
        )
        self.assertIsNotNone(payload.callchain_evidence)
        self.assertTrue(
            manifest_document["validation"]["stock_callchain_verified"]
        )
        self.assertTrue(
            manifest_document["validation"][
                "three_local_branch_targets_verified"
            ]
        )
        self.assertTrue(
            manifest_document["validation"][
                "global_key_callback_registration_unchanged"
            ]
        )
        self.assertTrue(
            manifest_document["validation"][
                "global_ui_timer_callback_registration_unchanged"
            ]
        )
        callchain_gates = manifest_document["callchain_gates"]
        self.assertEqual(
            callchain_gates["route_validation"]["local_branch_state_cases"],
            15,
        )
        self.assertIn(
            "retired_total_key_wrapper_absent",
            callchain_gates["disassembly"],
        )
        self.assertIn(
            "retired_window_navigation_absent",
            callchain_gates["disassembly"],
        )
        self.assertIn(
            "gif_failure_restore_call",
            callchain_gates["disassembly"],
        )
        self.assertIn(
            "local_branch_resume_targets",
            callchain_gates["disassembly"],
        )
        self.assertTrue(
            callchain_gates["disassembly"]["overview_right_stock_resume_only"]
        )
        self.assertTrue(callchain_gates["overview_right_stock_resume_only"])
        self.assertTrue(
            callchain_gates["disassembly"]["transport_symbols_absent"]
        )
        self.assertTrue(
            callchain_gates["disassembly"]["temporary_paths_absent"]
        )
        self.assertTrue(
            manifest_document["validation"]["stock_transport_paths_unchanged"]
        )
        lowered_disassembly = disassembly.lower()
        for symbol in LOCAL_UI_FORBIDDEN_SYMBOLS:
            self.assertNotIn(f"<{symbol}>:", lowered_disassembly)
        for address in LOCAL_UI_FORBIDDEN_CALLEES:
            self.assertNotIn(f"# {address:08x} <", lowered_disassembly)
        self.assertNotIn(b"/tmp/", payload_bytes)
        stage_bytes = self.stage.read_bytes()
        self.assertEqual(
            stage_bytes[
                PET_STATE_SIZE_OFFSET :
                PET_STATE_SIZE_OFFSET + len(PET_STATE_SIZE_ORIGINAL)
            ],
            PET_STATE_SIZE_ORIGINAL,
        )
        self.assertEqual(
            output_bytes[
                PET_STATE_SIZE_OFFSET :
                PET_STATE_SIZE_OFFSET + len(PET_STATE_SIZE_EXTENDED)
            ],
            PET_STATE_SIZE_EXTENDED,
        )
        self.assertEqual(
            output_bytes[HOOK_OFFSET : HOOK_OFFSET + len(HOOK_ORIGINAL)],
            stage_bytes[HOOK_OFFSET : HOOK_OFFSET + len(HOOK_ORIGINAL)],
        )
        self.assertEqual(
            output_bytes[
                TRAMPOLINE_OFFSET :
                TRAMPOLINE_OFFSET + len(TRAMPOLINE_ORIGINAL)
            ],
            stage_bytes[
                TRAMPOLINE_OFFSET :
                TRAMPOLINE_OFFSET + len(TRAMPOLINE_ORIGINAL)
            ],
        )
        for offset, original in (
            (KEY_CALLBACK_HIGH_OFFSET, KEY_CALLBACK_HIGH_ORIGINAL),
            (KEY_CALLBACK_LOW_OFFSET, KEY_CALLBACK_LOW_ORIGINAL),
            (UI_CALLBACK_LUI, INSTRUCTION_EXPECTED[UI_CALLBACK_LUI]),
            (UI_CALLBACK_ADDI, INSTRUCTION_EXPECTED[UI_CALLBACK_ADDI]),
        ):
            self.assertEqual(
                output_bytes[offset : offset + len(original)],
                original,
            )
            self.assertEqual(
                output_bytes[offset : offset + len(original)],
                stage_bytes[offset : offset + len(original)],
            )
        hook_offsets: set[int] = set()
        for (
            hook_offset,
            hook_original,
            trampoline_offset,
            symbol,
            _resume_address,
            _label,
        ) in STOCK_LOCAL_BRANCH_HOOKS:
            hook_offsets.update(
                range(hook_offset, hook_offset + len(hook_original))
            )
            self.assertEqual(
                stage_bytes[
                    hook_offset : hook_offset + len(hook_original)
                ],
                hook_original,
            )
            self.assertEqual(
                output_bytes[
                    hook_offset : hook_offset + len(hook_original)
                ],
                _encode_jal(
                    XIP_DELTA + hook_offset,
                    XIP_DELTA + trampoline_offset,
                ),
            )
            self.assertEqual(
                stage_bytes[trampoline_offset : trampoline_offset + 8],
                b"\0" * 8,
            )
            self.assertEqual(
                output_bytes[trampoline_offset : trampoline_offset + 8],
                _absolute_tail_jump(payload.symbols[symbol]),
            )
        callback_start, callback_end = STOCK_KEY_CALLBACK_RANGE
        for offset in range(callback_start, callback_end):
            if offset not in hook_offsets:
                self.assertEqual(output_bytes[offset], stage_bytes[offset])
        power_start, power_end = STOCK_POWER_CONFIRM_RANGE
        self.assertEqual(
            output_bytes[power_start:power_end],
            stage_bytes[power_start:power_end],
        )
        self.assertEqual(
            output_bytes[
                LOADER_TRAMPOLINE_OFFSET :
                LOADER_TRAMPOLINE_OFFSET + len(LOADER_TRAMPOLINE_ORIGINAL)
            ],
            LOADER_TRAMPOLINE_ORIGINAL,
        )
        for offset in (
            SINK_CALLBACK_LUI,
            SINK_CALLBACK_ADDI,
            HTTP_PERFORM_CALL,
            SUCCESS_TIMER_LUI,
            SUCCESS_TIMER_ADDI,
            SUCCESS_TIMER_REM,
            SUCCESS_TIMER_BASE_ADDI,
            SUCCESS_TIMER_ADD,
            FAILURE_BACKOFF_STORE,
        ):
            expected = INSTRUCTION_EXPECTED[offset]
            self.assertEqual(
                output_bytes[offset : offset + len(expected)],
                stage_bytes[offset : offset + len(expected)],
            )
        for offset, capacity, _expected, _label in URL_REGIONS:
            self.assertEqual(
                output_bytes[offset : offset + capacity],
                stage_bytes[offset : offset + capacity],
            )
        page_register = disassembly.split(
            "<ap01_agents_page_register>:", 1
        )[1].split("<ap01_agents_state_read>:", 1)[0]
        self.assertIn("ret", page_register)
        self.assertNotIn("call", page_register)
        for forbidden in (
            "# a00c1ec6 <lv_obj_create>",
            "# a01930fe <lv_gif_create>",
            "# a00bebee <lv_obj_del>",
            "# a00c5d84 <lv_obj_get_child>",
            "# a00c5fe4 <lv_obj_get_child_count>",
            "# a00b0290 <window_get_active>",
            "# a00b0570 <window_get_count>",
            "# a00b06f4 <window_set_active>",
            "# a00bbfee <stock_key_event>",
            "# a007e1c4 <malloc>",
            "# a007c256 <free>",
        ):
            self.assertNotIn(forbidden, disassembly)
        local_branches = disassembly.split(
            "<ap01_agents_stock_pet_left_entry>:", 1
        )[1].split("<ap01_agents_show_page>:", 1)[0]
        for marker in (
            "<ap01_agents_find_pet_state>",
            "<ap01_agents_state_read>",
            "<ap01_agents_show_page>",
            "<ap01_agents_restore_pet>",
            "<stock_pet_left_resume>",
            "<stock_pet_right_resume>",
            "<stock_pet_enter_resume>",
            "<stock_key_epilogue>",
        ):
            self.assertIn(marker, local_branches)
        self.assertNotIn("<stock_key_event>", local_branches)
        self.assertNotIn("<stock_switch_page>", local_branches)
        self.assertNotIn("<ap01_agents_key_event>:", disassembly)
        self.assertNotIn("<ap01_agents_stock_power_left_entry>:", disassembly)
        state_write = disassembly.split(
            "<ap01_agents_state_write>:", 1
        )[1].split("<ap01_agents_find_pet_state>:", 1)[0]
        self.assertIn("16(a0)", state_write)
        for offset in (0, 4, 8, 12):
            self.assertNotIn(f"{offset}(a0)", state_write)
        find_state = disassembly.split("<ap01_agents_find_pet_state>:", 1)[1].split(
            "<ap01_agents_stock_pet_left_entry>:", 1
        )[0]
        self.assertIn("li\ta1,7", find_state)
        self.assertIn("# a00be3ca <stock_get_child>", find_state)
        self.assertIn("16(a0)", find_state)
        self.assertIn("4(t0)", find_state)

    def test_stock_resume_builder_stops_before_writing_unresolved_route(
        self,
    ) -> None:
        if (
            not shutil.which("riscv64-elf-as")
            or not shutil.which("riscv64-elf-gcc")
        ):
            self.skipTest("本机没有阶段固件或固定编译工具")
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            output = root / LOCAL_UI_STOCK_RESUME_OUTPUT_FILENAME
            manifest = root / "manifest.json"
            with self.assertRaisesRegex(
                AgentsDashboardFirmwareError,
                "刷前连续页面事件模拟未通过",
            ):
                build_local_ui_stock_resume_firmware(
                    self.stage,
                    output,
                    manifest,
                    root / "firmware",
                    tool_revision={
                        "commit": "test",
                        "scoped_code_dirty": False,
                    },
                )
            self.assertFalse(output.exists())
            self.assertFalse(manifest.exists())

    def test_base_safe_builder_guards_power_and_passes_simulation(self) -> None:
        if (
            not shutil.which("riscv64-elf-as")
            or not shutil.which("riscv64-elf-gcc")
        ):
            self.skipTest("本机没有阶段固件或固定编译工具")
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            output = root / LOCAL_UI_BASE_SAFE_OUTPUT_FILENAME
            manifest = root / "manifest.json"
            result = build_local_ui_base_safe_firmware(
                self.stage,
                output,
                manifest,
                root / "firmware",
                tool_revision={
                    "commit": "test",
                    "scoped_code_dirty": False,
                },
            )
            document = json.loads(manifest.read_text(encoding="utf-8"))
            output_bytes = output.read_bytes()
            stage_bytes = self.stage.read_bytes()

        self.assertEqual(
            document["manifest_type"],
            "agents-local-ui-base-safe-firmware",
        )
        self.assertEqual(result.sha256, hashlib.sha256(output_bytes).hexdigest())
        self.assertTrue(document["interaction_simulation"]["summary"]["passed"])
        self.assertEqual(
            document["interaction_simulation"]["scope"]["configuration_cases"],
            4,
        )
        self.assertEqual(
            document["interaction_simulation"]["summary"][
                "exhaustive_sequence_count"
            ],
            4356,
        )
        self.assertTrue(
            document["validation"]["page_filter_switch_call_verified"]
        )
        self.assertTrue(document["validation"]["installation_allowed"])
        self.assertEqual(
            document["status"],
            "approved-for-one-test-installation",
        )
        self.assertTrue(
            document["callchain_gates"]["disassembly"][
                "overview_right_closes_state_without_gif_reset"
            ]
        )
        self.assertIn(
            "shared_page_filter_callchain",
            document["callchain_gates"]["disassembly"],
        )
        self.assertIn(
            "power_confirm_guard_callchain",
            document["callchain_gates"]["disassembly"],
        )
        power_start, power_end = STOCK_POWER_CONFIRM_RANGE
        guard_offset, guard_original, guard_trampoline, guard_symbol, *_ = (
            LOCAL_UI_POWER_CONFIRM_GUARD_HOOK
        )
        self.assertEqual(
            output_bytes[guard_offset : guard_offset + len(guard_original)],
            _encode_jal(
                XIP_DELTA + guard_offset,
                XIP_DELTA + guard_trampoline,
            ),
        )
        self.assertEqual(
            output_bytes[guard_offset + len(guard_original) : power_end],
            stage_bytes[guard_offset + len(guard_original) : power_end],
        )
        self.assertEqual(
            output_bytes[guard_trampoline : guard_trampoline + 8],
            _absolute_tail_jump(
                int(
                    document["callchain_gates"]["local_branch_hooks"][4][
                        "payload_address"
                    ],
                    16,
                )
            ),
        )
        self.assertEqual(
            document["callchain_gates"]["local_branch_hooks"][4][
                "payload_symbol"
            ],
            guard_symbol,
        )
        self.assertFalse(
            document["validation"]["stock_power_confirm_path_unchanged"]
        )
        self.assertTrue(
            document["validation"]["stock_power_confirm_entry_guarded"]
        )
        filter_offset, filter_original, filter_trampoline, symbol, *_ = (
            LOCAL_UI_SHARED_PAGE_FILTER_HOOK
        )
        self.assertEqual(
            output_bytes[filter_offset : filter_offset + len(filter_original)],
            _encode_jal(
                XIP_DELTA + filter_offset,
                XIP_DELTA + filter_trampoline,
            ),
        )
        self.assertEqual(
            output_bytes[filter_trampoline : filter_trampoline + 8],
            _absolute_tail_jump(
                int(
                    document["callchain_gates"]["local_branch_hooks"][3][
                        "payload_address"
                    ],
                    16,
                )
            ),
        )
        self.assertEqual(
            document["callchain_gates"]["local_branch_hooks"][3][
                "payload_symbol"
            ],
            symbol,
        )

    def test_rejected_local_ui_power_safe_builder_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            with self.assertRaisesRegex(
                AgentsDashboardFirmwareError,
                "功率路径隔离版已因功率页确认卡住停用",
            ):
                build_local_ui_power_safe_firmware(
                    self.stage,
                    root / LOCAL_UI_POWER_SAFE_OUTPUT_FILENAME,
                    root / "manifest.json",
                    root / "firmware",
                    tool_revision={"commit": "test", "scoped_code_dirty": False},
                )

    def test_rejected_stock_safe_builder_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            with self.assertRaisesRegex(
                AgentsDashboardFirmwareError,
                "FW-AGENTS-009 已因缺少基座生命周期保护停用",
            ):
                build_local_ui_stock_safe_firmware(
                    self.stage,
                    root / LOCAL_UI_STOCK_SAFE_OUTPUT_FILENAME,
                    root / "manifest.json",
                    root / "firmware",
                    tool_revision={"commit": "test", "scoped_code_dirty": False},
                )

    def test_stock_local_branches_cover_all_states(self) -> None:
        report = validate_stock_local_branch_routes()
        self.assertEqual(report["local_branch_state_cases"], 15)
        self.assertEqual(report["detail_rotation_cases"], 6)
        self.assertEqual(report["disabled_page_cases"], 2)
        self.assertEqual(
            route_stock_local_branch("pet-left", 0).action,
            "stock-resume",
        )
        self.assertEqual(
            route_stock_local_branch("pet-right", 0).target_state,
            1,
        )
        overview_right = route_stock_local_branch("pet-right", 1)
        self.assertEqual(overview_right.action, "close-then-stock-resume")
        self.assertEqual(overview_right.target_state, 0)
        self.assertIsNone(overview_right.target_dispatch)
        self.assertIsNone(overview_right.switch_mode)
        self.assertEqual(
            route_stock_local_branch("pet-enter", 1).target_state,
            2,
        )
        for state in (2, 3, 4):
            self.assertEqual(
                route_stock_local_branch("pet-enter", state).target_state,
                1,
            )
        self.assertEqual(
            route_stock_local_branch(
                "pet-left",
                1,
                pet_enabled=False,
            ).target_dispatch,
            6,
        )
        self.assertEqual(
            route_stock_local_branch(
                "pet-right",
                0,
                agents_enabled=False,
            ).action,
            "stock-resume",
        )

    def test_failed_full_integration_candidate_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            output = root / OPT_REWRITE_OUTPUT_FILENAME
            manifest = root / "manifest.json"
            with self.assertRaisesRegex(
                RuntimeError,
                "不属于已记录的局部分支方案",
            ):
                build_sync_firmware(
                    self.stage,
                    output,
                    manifest,
                    root / "firmware",
                    url_base="http://10.0.0.11:18765/a",
                    refresh_seconds=300,
                    tool_revision={
                        "commit": "test",
                        "scoped_code_dirty": False,
                    },
                    expected_output_name=OPT_REWRITE_OUTPUT_FILENAME,
                    reuse_stock_pet=True,
                )
            self.assertFalse(output.exists())

    def test_independent_tail_detects_all_defined_corruption_classes(self) -> None:
        for state in range(5):
            encoded = encode_agents_state(state)
            self.assertEqual(decode_agents_state(encoded), state)
        for encoded in (
            0,
            0xA50000FF,
            0xA50101FF,
            encode_agents_state(4) ^ 1,
            0xA50105FA,
        ):
            self.assertIsNone(decode_agents_state(encoded))

    def test_retired_stock_reuse_name_cannot_build(self) -> None:
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            with self.assertRaisesRegex(
                RuntimeError,
                "低栈局部分支成品已因功率页确认重启停用",
            ):
                build_low_stack_local_branches_firmware(
                    self.stage,
                    root / LOW_STACK_LOCAL_BRANCHES_OUTPUT_FILENAME,
                    root / "retired-manifest.json",
                    root / "retired-build",
                    url_base="http://10.0.0.10:8765/a",
                    refresh_seconds=300,
                    tool_revision={
                        "commit": "test",
                        "scoped_code_dirty": False,
                    },
                )
            retired = "ap01-1.0.2_0031-agents-stock-dispatch-observation.bin"
            with self.assertRaisesRegex(
                RuntimeError,
                "不属于已记录的局部分支方案",
            ):
                build_sync_firmware(
                    self.stage,
                    root / retired,
                    root / "manifest.json",
                    root / "build",
                    url_base="http://10.0.0.10:8765/a",
                    refresh_seconds=300,
                    tool_revision={
                        "commit": "test",
                        "scoped_code_dirty": False,
                    },
                    expected_output_name=retired,
                    reuse_stock_pet=True,
                )

        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            with self.assertRaisesRegex(
                RuntimeError,
                "功率页确认重启停用",
            ):
                build_stock_callchain_firmware(
                    self.stage,
                    root / STOCK_CALLCHAIN_OUTPUT_FILENAME,
                    root / "manifest.json",
                    root / "build",
                    url_base="http://10.0.0.10:8765/a",
                    refresh_seconds=300,
                    tool_revision={
                        "commit": "test",
                        "scoped_code_dirty": False,
                    },
                )

        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            with self.assertRaisesRegex(
                RuntimeError,
                "功率页确认卡死停用",
            ):
                build_stock_enter_gate_firmware(
                    self.stage,
                    root / STOCK_ENTER_GATE_OUTPUT_FILENAME,
                    root / "manifest.json",
                    root / "build",
                    url_base="http://10.0.0.10:8765/a",
                    refresh_seconds=300,
                    tool_revision={
                        "commit": "test",
                        "scoped_code_dirty": False,
                    },
                )

    def test_request_formats_fit_without_positional_printf(self) -> None:
        location, city = _request_formats()
        self.assertLessEqual(len(location) + 1, 44)
        self.assertLessEqual(len(city) + 1, 48)
        self.assertNotIn(b"$", location)
        self.assertNotIn(b"$", city)
        self.assertEqual(location, b"%s")
        self.assertEqual(city, b"%s")
        self.assertNotIn(b"?", location + city)

    def test_live_data_location_independent_firmware_passes_all_build_gates(
        self,
    ) -> None:
        if (
            not shutil.which("riscv64-elf-as")
            or not shutil.which("riscv64-elf-gcc")
        ):
            self.skipTest("本机没有阶段固件或固定编译工具")
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            output = root / LIVE_DATA_LOCATION_INDEPENDENT_OUTPUT_FILENAME
            manifest = root / "manifest.json"
            result = build_live_data_location_independent_firmware(
                self.stage,
                output,
                manifest,
                root / "payload",
                url_base="http://10.0.0.11:18765/a",
                refresh_seconds=300,
                tool_revision={
                    "commit": "test",
                    "scoped_code_dirty": False,
                },
            )
            document = json.loads(manifest.read_text(encoding="utf-8"))
            output_bytes = output.read_bytes()

        self.assertEqual(
            document["manifest_type"],
            "agents-live-data-location-independent-firmware",
        )
        self.assertEqual(
            result.output.name,
            LIVE_DATA_LOCATION_INDEPENDENT_OUTPUT_FILENAME,
        )
        self.assertTrue(document["transport"]["enabled"])
        self.assertEqual(
            document["transport"]["url_base"],
            "http://10.0.0.11:18765/a",
        )
        self.assertEqual(document["transport"]["refresh_seconds"], 300)
        self.assertEqual(document["transport"]["location_request_format"], "%s")
        self.assertEqual(document["transport"]["city_request_format"], "%s")
        self.assertTrue(document["transport"]["ui_timer_wrapper_enabled"])
        self.assertTrue(
            document["transport"]["weather_location_dependency_removed"]
        )
        self.assertFalse(
            document["transport"]["location_placeholder_transmitted"]
        )
        self.assertFalse(
            document["transport"]["shared_device_configuration_used"]
        )
        self.assertTrue(document["validation"]["transport_symbols_present"])
        self.assertFalse(
            document["validation"][
                "global_ui_timer_callback_registration_unchanged"
            ]
        )
        self.assertTrue(
            document["validation"]["global_ui_timer_calls_stock_first"]
        )
        self.assertTrue(
            document["validation"]["stock_power_confirm_entry_guarded"]
        )
        self.assertTrue(document["validation"]["installation_allowed"])
        self.assertTrue(document["interaction_simulation"]["summary"]["passed"])
        self.assertTrue(document["callchain_gates"]["stock_transport_scoped_patch"])
        self.assertTrue(
            document["callchain_gates"][
                "stock_location_lookup_scoped_patch"
            ]
        )
        self.assertEqual(
            document["callchain_gates"]["stock_location_lookup"][
                "payload_symbol"
            ],
            "ap01_agents_location_stub",
        )
        self.assertLessEqual(document["payload"]["maximum_static_stack"], 96)
        self.assertNotEqual(
            output_bytes[
                UI_CALLBACK_LUI : UI_CALLBACK_LUI + len(
                    INSTRUCTION_EXPECTED[UI_CALLBACK_LUI]
                )
            ],
            INSTRUCTION_EXPECTED[UI_CALLBACK_LUI],
        )
        for offset, capacity, _expected, label in URL_REGIONS:
            value = output_bytes[offset : offset + capacity].split(b"\0", 1)[0]
            if "格式" in label:
                self.assertEqual(value, b"%s")
        self.assertNotEqual(
            output_bytes[
                LOCATION_LOOKUP_CALL :
                LOCATION_LOOKUP_CALL + len(
                    INSTRUCTION_EXPECTED[LOCATION_LOOKUP_CALL]
                )
            ],
            INSTRUCTION_EXPECTED[LOCATION_LOOKUP_CALL],
        )
        self.assertEqual(
            self.stage.read_bytes()[
                LOCATION_TRAMPOLINE_OFFSET :
                LOCATION_TRAMPOLINE_OFFSET + len(
                    LOCATION_TRAMPOLINE_ORIGINAL
                )
            ],
            LOCATION_TRAMPOLINE_ORIGINAL,
        )
        self.assertNotEqual(
            output_bytes[
                LOCATION_TRAMPOLINE_OFFSET :
                LOCATION_TRAMPOLINE_OFFSET + len(
                    LOCATION_TRAMPOLINE_ORIGINAL
                )
            ],
            LOCATION_TRAMPOLINE_ORIGINAL,
        )

    def test_live_data_validated_package_is_distinct_and_installable_once(
        self,
    ) -> None:
        if (
            not shutil.which("riscv64-elf-as")
            or not shutil.which("riscv64-elf-gcc")
        ):
            self.skipTest("本机没有阶段固件或固定编译工具")
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            output = root / LIVE_DATA_VALIDATED_PACKAGE_OUTPUT_FILENAME
            manifest = root / "manifest.json"
            result = build_live_data_validated_package_firmware(
                self.stage,
                output,
                manifest,
                root / "payload",
                url_base="http://10.0.0.11:18765/a",
                refresh_seconds=300,
                tool_revision={
                    "commit": "test",
                    "scoped_code_dirty": False,
                },
            )
            document = json.loads(manifest.read_text(encoding="utf-8"))

        self.assertEqual(
            document["manifest_type"],
            "agents-live-data-validated-package-firmware",
        )
        self.assertEqual(
            result.output.name,
            LIVE_DATA_VALIDATED_PACKAGE_OUTPUT_FILENAME,
        )
        self.assertEqual(
            document["status"], "approved-for-one-test-installation"
        )
        self.assertTrue(document["transport"]["gif_structural_validation"])
        self.assertTrue(document["transport"]["gif_trailer_validation"])
        self.assertTrue(document["transport"]["single_frame_rejected"])
        self.assertTrue(
            document["transport"]["unpublished_slot_cleared_on_failure"]
        )
        self.assertEqual(document["transport"]["download_state_bytes"], 136)
        self.assertTrue(document["validation"]["installation_allowed"])
        self.assertTrue(document["interaction_simulation"]["summary"]["passed"])
        self.assertLessEqual(document["payload"]["maximum_static_stack"], 96)

    def test_live_data_endpoint_failover_is_ordered_and_not_installable(
        self,
    ) -> None:
        if (
            not shutil.which("riscv64-elf-as")
            or not shutil.which("riscv64-elf-gcc")
        ):
            self.skipTest("本机没有阶段固件或固定编译工具")
        endpoints = tuple(
            f"http://10.0.0.{index}:18765/a" for index in range(1, 11)
        )
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            output = root / LIVE_DATA_ENDPOINT_FAILOVER_OUTPUT_FILENAME
            manifest = root / "manifest.json"
            result = build_live_data_endpoint_failover_firmware(
                self.stage,
                output,
                manifest,
                root / "payload",
                endpoints=endpoints,
                endpoint_timeout_seconds=3,
                refresh_seconds=300,
                tool_revision={
                    "commit": "test",
                    "scoped_code_dirty": False,
                },
            )
            document = json.loads(manifest.read_text(encoding="utf-8"))
            output_bytes = output.read_bytes()

        self.assertEqual(
            document["manifest_type"],
            "agents-live-data-endpoint-failover-firmware",
        )
        self.assertEqual(
            result.output.name,
            LIVE_DATA_ENDPOINT_FAILOVER_OUTPUT_FILENAME,
        )
        self.assertEqual(document["status"], "built-not-approved-for-installation")
        self.assertTrue(document["transport"]["endpoint_failover_enabled"])
        self.assertEqual(document["transport"]["endpoint_priority"], list(endpoints))
        self.assertEqual(document["transport"]["endpoint_timeout_seconds"], 3)
        self.assertTrue(document["transport"]["retry_starts_at_first_endpoint"])
        self.assertFalse(document["validation"]["installation_allowed"])
        self.assertTrue(document["validation"]["transport_symbols_present"])
        self.assertIn(endpoints[0].encode("ascii"), output_bytes)
        self.assertIn(endpoints[1].encode("ascii"), output_bytes)
        self.assertLessEqual(document["payload"]["maximum_static_stack"], 96)

    def test_fixed_primary_pages_candidate_is_installable_and_hidden(self) -> None:
        if (
            not shutil.which("riscv64-elf-as")
            or not shutil.which("riscv64-elf-gcc")
        ):
            self.skipTest("本机没有阶段固件或固定编译工具")
        endpoints = (
            "http://10.0.0.10:18765/a",
            "http://10.0.0.11:18765/a",
        )
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            result = build_live_data_fixed_primary_pages_firmware(
                self.stage,
                root / LIVE_DATA_FIXED_PRIMARY_PAGES_OUTPUT_FILENAME,
                root / "manifest.json",
                root / "payload",
                endpoints=endpoints,
                endpoint_timeout_seconds=3,
                refresh_seconds=300,
                tool_revision={"commit": "test", "scoped_code_dirty": False},
            )
            document = json.loads(
                result.manifest.read_text(encoding="utf-8")
            )

        self.assertEqual(
            document["manifest_type"],
            "agents-live-data-fixed-primary-pages-v2-firmware",
        )
        self.assertTrue(document["validation"]["installation_allowed"])
        self.assertTrue(
            document["validation"]["calendar_skip_direction_verified"]
        )
        self.assertTrue(
            document["validation"][
                "overview_left_gif_preserved_until_switch"
            ]
        )
        self.assertEqual(
            document["transport"]["fixed_hidden_primary_pages"],
            ["calendar", "pet"],
        )
        self.assertTrue(document["interaction_simulation"]["summary"]["passed"])
        overview_left = document["interaction_simulation"][
            "selected_traces"
        ]["overview-left-exit"][0]
        self.assertEqual(overview_left["after"]["visible_page"], "settings")
        self.assertEqual(overview_left["intermediate_visible_pages"], [])

    def test_rejected_weather_coexistence_build_cannot_be_recreated(self) -> None:
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            with self.assertRaisesRegex(
                AgentsDashboardFirmwareError,
                "FW-AGENTS-017 已因天气恢复但看板未发布停用",
            ):
                build_live_data_weather_coexistence_firmware(
                    self.stage,
                    root / LIVE_DATA_WEATHER_COEXISTENCE_OUTPUT_FILENAME,
                    root / "manifest.json",
                    root / "payload",
                    endpoints=("http://10.0.0.10:18765/a",),
                    endpoint_timeout_seconds=3,
                    refresh_seconds=300,
                    tool_revision={"commit": "test", "scoped_code_dirty": False},
                )

    def test_adoption_diagnostic_preserves_stock_request_regions(self) -> None:
        if (
            not shutil.which("riscv64-elf-as")
            or not shutil.which("riscv64-elf-gcc")
        ):
            self.skipTest("本机没有阶段固件或固定编译工具")
        endpoints = (
            "http://10.0.0.10:18765/a",
            "http://10.0.0.11:18765/a",
        )
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            result = build_live_data_adoption_diagnostic_firmware(
                self.stage,
                root / LIVE_DATA_ADOPTION_DIAGNOSTIC_OUTPUT_FILENAME,
                root / "manifest.json",
                root / "payload",
                endpoints=endpoints,
                endpoint_timeout_seconds=3,
                refresh_seconds=300,
                tool_revision={"commit": "test", "scoped_code_dirty": False},
            )
            document = json.loads(result.manifest.read_text(encoding="utf-8"))
            output_bytes = result.output.read_bytes()
            stage_bytes = self.stage.read_bytes()

        self.assertEqual(
            document["manifest_type"],
            "agents-adoption-diagnostic-firmware",
        )
        self.assertTrue(document["validation"]["installation_allowed"])
        self.assertTrue(document["transport"]["stock_weather_preserved"])
        self.assertTrue(
            document["transport"]["agents_location_fallback_enabled"]
        )
        self.assertTrue(
            document["transport"]["weather_and_agents_results_isolated"]
        )
        self.assertTrue(
            document["transport"]["weather_and_agents_round_robin"]
        )
        self.assertFalse(document["transport"]["download_diagnostic_enabled"])
        self.assertFalse(document["transport"]["result_diagnostic_enabled"])
        self.assertFalse(document["transport"]["publish_diagnostic_enabled"])
        self.assertTrue(document["transport"]["adoption_diagnostic_enabled"])
        self.assertFalse(document["transport"]["round_diagnostic_enabled"])
        self.assertTrue(
            document["transport"]["single_business_result_per_round"]
        )
        self.assertTrue(document["transport"]["stock_request_regions_unchanged"])
        self.assertTrue(document["transport"]["stock_download_callback_unchanged"])
        self.assertFalse(
            document["transport"]["weather_location_dependency_removed"]
        )
        for offset, capacity, _expected, _label in URL_REGIONS:
            self.assertEqual(
                output_bytes[offset : offset + capacity],
                stage_bytes[offset : offset + capacity],
            )
        for offset in (SINK_CALLBACK_LUI, SINK_CALLBACK_ADDI):
            expected = INSTRUCTION_EXPECTED[offset]
            self.assertEqual(
                output_bytes[offset : offset + len(expected)],
                expected,
            )
        self.assertNotEqual(
            output_bytes[
                LOCATION_LOOKUP_CALL :
                LOCATION_LOOKUP_CALL + len(INSTRUCTION_EXPECTED[LOCATION_LOOKUP_CALL])
            ],
            INSTRUCTION_EXPECTED[LOCATION_LOOKUP_CALL],
        )
        self.assertNotEqual(
            output_bytes[
                HTTP_PERFORM_CALL :
                HTTP_PERFORM_CALL + len(INSTRUCTION_EXPECTED[HTTP_PERFORM_CALL])
            ],
            INSTRUCTION_EXPECTED[HTTP_PERFORM_CALL],
        )
        self.assertLessEqual(document["payload"]["maximum_static_stack"], 96)

    def test_stable_adoption_has_no_diagnostic_source_switches(self) -> None:
        if (
            not shutil.which("riscv64-elf-as")
            or not shutil.which("riscv64-elf-gcc")
        ):
            self.skipTest("本机没有阶段固件或固定编译工具")
        endpoints = (
            "http://10.0.0.10:18765/a",
            "http://10.0.0.11:18765/a",
        )
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            result = build_live_data_stable_adoption_firmware(
                self.stage,
                root / LIVE_DATA_STABLE_ADOPTION_OUTPUT_FILENAME,
                root / "manifest.json",
                root / "payload",
                endpoints=endpoints,
                endpoint_timeout_seconds=3,
                refresh_seconds=300,
                tool_revision={"commit": "test", "scoped_code_dirty": False},
            )
            document = json.loads(result.manifest.read_text(encoding="utf-8"))
            disassembly = (
                root / "payload" / "agents-sync.disassembly.txt"
            ).read_text(encoding="utf-8")

        self.assertEqual(
            document["manifest_type"], "agents-stable-adoption-firmware"
        )
        self.assertTrue(document["validation"]["installation_allowed"])
        self.assertTrue(document["transport"]["stock_weather_preserved"])
        self.assertTrue(document["transport"]["weather_and_agents_round_robin"])
        for key in (
            "round_diagnostic_enabled",
            "download_diagnostic_enabled",
            "result_diagnostic_enabled",
            "publish_diagnostic_enabled",
            "adoption_diagnostic_enabled",
        ):
            self.assertFalse(document["transport"][key])
        self.assertNotIn("<agents_diagnostic_show>", disassembly)
        self.assertNotIn("<agents_diagnostic_set_source>", disassembly)
        self.assertLessEqual(document["payload"]["maximum_static_stack"], 96)

    def test_weather_agents_dual_request_is_scoped_to_new_candidate(self) -> None:
        if (
            not shutil.which("riscv64-elf-as")
            or not shutil.which("riscv64-elf-gcc")
        ):
            self.skipTest("本机没有阶段固件或固定编译工具")
        endpoints = (
            "http://10.0.0.10:18765/a",
            "http://10.0.0.11:18765/a",
        )
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            result = build_live_data_weather_agents_dual_request_firmware(
                self.stage,
                root / LIVE_DATA_WEATHER_AGENTS_DUAL_REQUEST_OUTPUT_FILENAME,
                root / "manifest.json",
                root / "payload",
                endpoints=endpoints,
                endpoint_timeout_seconds=3,
                refresh_seconds=300,
                tool_revision={"commit": "test", "scoped_code_dirty": False},
            )
            document = json.loads(result.manifest.read_text(encoding="utf-8"))
            endpoint_header = (root / "payload" / "endpoint-config.h").read_text(
                encoding="ascii"
            )

        self.assertEqual(
            document["manifest_type"],
            "agents-weather-agents-dual-request-firmware",
        )
        self.assertTrue(document["validation"]["installation_allowed"])
        self.assertTrue(document["transport"]["stock_weather_preserved"])
        self.assertTrue(document["transport"]["weather_and_agents_dual_request"])
        self.assertFalse(document["transport"]["weather_and_agents_round_robin"])
        self.assertFalse(document["transport"]["single_business_result_per_round"])
        self.assertIn(
            "#define AP01_AGENTS_WEATHER_DUAL_REQUEST 1u",
            endpoint_header,
        )

    def test_stock_https_dual_request_patches_both_network_calls(self) -> None:
        if (
            not shutil.which("riscv64-elf-as")
            or not shutil.which("riscv64-elf-gcc")
        ):
            self.skipTest("本机没有阶段固件或固定编译工具")
        endpoints = (
            "http://10.0.0.10:18765/a",
            "http://10.0.0.11:18765/a",
        )
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            result = build_live_data_stock_https_dual_request_firmware(
                self.stage,
                root / LIVE_DATA_STOCK_HTTPS_DUAL_REQUEST_OUTPUT_FILENAME,
                root / "manifest.json",
                root / "payload",
                endpoints=endpoints,
                endpoint_timeout_seconds=3,
                refresh_seconds=300,
                tool_revision={"commit": "test", "scoped_code_dirty": False},
            )
            document = json.loads(result.manifest.read_text(encoding="utf-8"))
            output_bytes = result.output.read_bytes()

        self.assertEqual(
            document["manifest_type"],
            "agents-stock-https-dual-request-firmware",
        )
        self.assertTrue(document["validation"]["installation_allowed"])
        self.assertTrue(document["transport"]["stock_weather_preserved"])
        self.assertTrue(document["transport"]["weather_and_agents_dual_request"])
        self.assertTrue(document["transport"]["stock_https_network_call_patched"])
        self.assertEqual(
            document["callchain_gates"]["stock_https_webclient_call"][
                "call_file_offset"
            ],
            f"0x{HTTPS_PERFORM_CALL:06x}",
        )
        self.assertNotEqual(
            output_bytes[
                HTTPS_PERFORM_CALL :
                HTTPS_PERFORM_CALL + len(INSTRUCTION_EXPECTED[HTTPS_PERFORM_CALL])
            ],
            INSTRUCTION_EXPECTED[HTTPS_PERFORM_CALL],
        )
        self.assertNotEqual(
            output_bytes[
                HTTP_PERFORM_CALL :
                HTTP_PERFORM_CALL + len(INSTRUCTION_EXPECTED[HTTP_PERFORM_CALL])
            ],
            INSTRUCTION_EXPECTED[HTTP_PERFORM_CALL],
        )

    def test_rejected_weather_hidden_dashboard_build_cannot_be_recreated(self) -> None:
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            with self.assertRaises(AgentsDashboardFirmwareError):
                build_live_data_weather_hidden_dashboard_firmware(
                    self.stage,
                    root / LIVE_DATA_WEATHER_HIDDEN_DASHBOARD_OUTPUT_FILENAME,
                    root / "manifest.json",
                    root / "payload",
                    endpoints=(
                        "http://10.0.0.10:18765/a",
                        "http://10.0.0.11:18765/a",
                    ),
                    endpoint_timeout_seconds=3,
                    refresh_seconds=300,
                    tool_revision={"commit": "test", "scoped_code_dirty": False},
                )

    def test_weather_hidden_dashboard_v2_hides_weather_and_uses_stock_https_path(self) -> None:
        if (
            not shutil.which("riscv64-elf-as")
            or not shutil.which("riscv64-elf-gcc")
        ):
            self.skipTest("本机没有阶段固件或固定编译工具")
        endpoints = tuple(
            f"http://10.0.0.{index}:18765/a" for index in range(1, 11)
        )
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            result = build_live_data_weather_hidden_dashboard_v2_firmware(
                self.stage,
                root / LIVE_DATA_WEATHER_HIDDEN_DASHBOARD_V2_OUTPUT_FILENAME,
                root / "manifest.json",
                root / "payload",
                endpoints=endpoints,
                endpoint_timeout_seconds=3,
                refresh_seconds=300,
                tool_revision={"commit": "test", "scoped_code_dirty": False},
            )
            document = json.loads(result.manifest.read_text(encoding="utf-8"))
            output_bytes = result.output.read_bytes()
            disassembly = (root / "payload" / "agents-sync.disassembly.txt").read_text(
                encoding="utf-8"
            )
            endpoint_header = (root / "payload" / "endpoint-config.h").read_text(
                encoding="ascii"
            )

        self.assertEqual(
            document["manifest_type"],
            "agents-weather-hidden-dashboard-v2-firmware",
        )
        self.assertEqual(document["transport"]["endpoint_priority"], list(endpoints))
        self.assertIn("#define AP01_AGENTS_ENDPOINT_COUNT 10u", endpoint_header)
        for index, endpoint in enumerate(endpoints, start=1):
            self.assertIn(
                f'#define AP01_AGENTS_ENDPOINT_{index} "{endpoint}"',
                endpoint_header,
            )
            self.assertIn(endpoint.encode("ascii"), output_bytes)
        self.assertTrue(document["validation"]["installation_allowed"])
        self.assertTrue(document["transport"]["weather_hidden_primary_page"])
        self.assertEqual(
            document["transport"]["fixed_hidden_primary_pages"],
            ["calendar", "weather", "pet"],
        )
        self.assertTrue(document["transport"]["stock_https_network_call_patched"])
        self.assertTrue(document["transport"]["weather_and_agents_dual_request"])
        self.assertTrue(document["validation"]["weather_skip_direction_verified"])
        self.assertIn("c.li\tx5,5", disassembly)
        self.assertGreaterEqual(disassembly.count("c.li\tx9,7"), 2)
        self.assertNotEqual(
            output_bytes[
                HTTPS_PERFORM_CALL :
                HTTPS_PERFORM_CALL + len(INSTRUCTION_EXPECTED[HTTPS_PERFORM_CALL])
            ],
            INSTRUCTION_EXPECTED[HTTPS_PERFORM_CALL],
        )
        self.assertNotEqual(
            output_bytes[
                HTTP_PERFORM_CALL :
                HTTP_PERFORM_CALL + len(INSTRUCTION_EXPECTED[HTTP_PERFORM_CALL])
            ],
            INSTRUCTION_EXPECTED[HTTP_PERFORM_CALL],
        )

    def test_public_firmware_contains_no_endpoint_and_requires_personalization(
        self,
    ) -> None:
        if (
            not shutil.which("riscv64-elf-as")
            or not shutil.which("riscv64-elf-gcc")
        ):
            self.skipTest("本机没有阶段固件或固定编译工具")
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            result = build_live_data_weather_hidden_dashboard_v2_firmware(
                self.stage,
                root / PUBLIC_FIRMWARE_OUTPUT_FILENAME,
                root / "manifest.json",
                root / "payload",
                endpoints=(),
                endpoint_timeout_seconds=0,
                refresh_seconds=300,
                tool_revision={"commit": "test", "scoped_code_dirty": False},
                standalone_timer=True,
            )
            document = json.loads(result.manifest.read_text(encoding="utf-8"))
            output_bytes = result.output.read_bytes()
            endpoint_header = (root / "payload" / "endpoint-config.h").read_text(
                encoding="ascii"
            )

        self.assertEqual(document["status"], "requires-endpoint-personalization")
        self.assertFalse(document["device_specific"])
        self.assertFalse(document["validation"]["installation_allowed"])
        self.assertFalse(document["transport"]["enabled"])
        self.assertTrue(document["transport"]["endpoint_configuration_required"])
        self.assertEqual(document["transport"]["endpoint_priority"], [])
        self.assertFalse(document["completeness"]["complete"])
        self.assertIn(
            "缺少服务端地址，需要根据用户实时局域网 IPv4 制作个人固件；"
            "刷机前应一次填入 1～10 个可用服务端地址",
            document["completeness"]["missing_items"],
        )
        self.assertTrue(document["endpoint_personalization"]["supported"])
        self.assertTrue(
            document["endpoint_personalization"]["required_before_install"]
        )
        self.assertTrue(
            document["endpoint_personalization"]["multiple_addresses_supported"]
        )
        self.assertEqual(document["endpoint_personalization"]["min_endpoint_count"], 1)
        self.assertEqual(document["endpoint_personalization"]["max_endpoint_count"], 10)
        self.assertIsNone(document["transport"]["url_base"])
        self.assertEqual(
            document["input"]["path"],
            f"artifacts/firmware/{self.stage.name}",
        )
        self.assertEqual(
            document["output"]["path"],
            f"artifacts/firmware/{PUBLIC_FIRMWARE_OUTPUT_FILENAME}",
        )
        self.assertIn("#define AP01_AGENTS_ENDPOINT_COUNT 0u", endpoint_header)
        self.assertIn("#define AP01_AGENTS_DISABLE_DOWNLOAD 1u", endpoint_header)
        self.assertNotIn("AP01_AGENTS_ENDPOINT_1", endpoint_header)
        self.assertNotIn(b"http://10.0.0.10", output_bytes)

    def test_weather_preserved_dual_request_requires_stock_weather_success(self) -> None:
        if (
            not shutil.which("riscv64-elf-as")
            or not shutil.which("riscv64-elf-gcc")
        ):
            self.skipTest("本机没有阶段固件或固定编译工具")
        endpoints = (
            "http://10.0.0.10:18765/a",
            "http://10.0.0.11:18765/a",
        )
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            result = build_live_data_weather_preserved_dual_request_firmware(
                self.stage,
                root / LIVE_DATA_WEATHER_PRESERVED_DUAL_REQUEST_OUTPUT_FILENAME,
                root / "manifest.json",
                root / "payload",
                endpoints=endpoints,
                endpoint_timeout_seconds=3,
                refresh_seconds=300,
                tool_revision={"commit": "test", "scoped_code_dirty": False},
            )
            document = json.loads(result.manifest.read_text(encoding="utf-8"))

        self.assertEqual(
            document["manifest_type"],
            "agents-weather-preserved-dual-request-firmware",
        )
        self.assertTrue(document["validation"]["installation_allowed"])
        self.assertTrue(document["transport"]["weather_and_agents_dual_request"])
        self.assertTrue(document["transport"]["stock_https_network_call_patched"])
        self.assertTrue(
            document["transport"]["weather_success_requires_stock_weather_request"]
        )
        self.assertFalse(document["transport"]["weather_stock_first"])

    def test_weather_stock_first_dual_request_disables_placeholder_round(self) -> None:
        if (
            not shutil.which("riscv64-elf-as")
            or not shutil.which("riscv64-elf-gcc")
        ):
            self.skipTest("本机没有阶段固件或固定编译工具")
        endpoints = (
            "http://10.0.0.10:18765/a",
            "http://10.0.0.11:18765/a",
        )
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            result = build_live_data_weather_stock_first_dual_request_firmware(
                self.stage,
                root / LIVE_DATA_WEATHER_STOCK_FIRST_DUAL_REQUEST_OUTPUT_FILENAME,
                root / "manifest.json",
                root / "payload",
                endpoints=endpoints,
                endpoint_timeout_seconds=3,
                refresh_seconds=300,
                tool_revision={"commit": "test", "scoped_code_dirty": False},
            )
            document = json.loads(result.manifest.read_text(encoding="utf-8"))
            disassembly = (
                root / "payload" / "agents-sync.disassembly.txt"
            ).read_text(encoding="utf-8")

        self.assertEqual(
            document["manifest_type"],
            "agents-weather-stock-first-dual-request-firmware",
        )
        self.assertTrue(document["validation"]["installation_allowed"])
        self.assertTrue(document["transport"]["weather_and_agents_dual_request"])
        self.assertTrue(document["transport"]["stock_https_network_call_patched"])
        self.assertTrue(
            document["transport"]["weather_success_requires_stock_weather_request"]
        )
        self.assertTrue(document["transport"]["weather_stock_first"])
        location_block = disassembly.split(
            "<ap01_agents_location_stub>:", 1
        )[1].split("<ap01_agents_webclient_wrapper>:", 1)[0]
        self.assertNotIn("sb\tx", location_block)

    def test_weather_solo_request_returns_after_stock_weather(self) -> None:
        if (
            not shutil.which("riscv64-elf-as")
            or not shutil.which("riscv64-elf-gcc")
        ):
            self.skipTest("本机没有阶段固件或固定编译工具")
        endpoints = (
            "http://10.0.0.10:18765/a",
            "http://10.0.0.11:18765/a",
        )
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            result = build_live_data_weather_solo_request_firmware(
                self.stage,
                root / LIVE_DATA_WEATHER_SOLO_REQUEST_OUTPUT_FILENAME,
                root / "manifest.json",
                root / "payload",
                endpoints=endpoints,
                endpoint_timeout_seconds=3,
                refresh_seconds=300,
                tool_revision={"commit": "test", "scoped_code_dirty": False},
            )
            document = json.loads(result.manifest.read_text(encoding="utf-8"))
            endpoint_header = (root / "payload" / "endpoint-config.h").read_text(
                encoding="ascii"
            )

        self.assertEqual(
            document["manifest_type"],
            "agents-weather-solo-request-firmware",
        )
        self.assertTrue(document["validation"]["installation_allowed"])
        self.assertFalse(document["transport"]["weather_and_agents_dual_request"])
        self.assertTrue(document["transport"]["weather_solo_request"])
        self.assertTrue(document["transport"]["stock_https_network_call_patched"])
        self.assertTrue(
            document["transport"]["weather_success_requires_stock_weather_request"]
        )
        self.assertTrue(document["transport"]["weather_stock_first"])
        self.assertTrue(document["transport"]["single_business_result_per_round"])
        self.assertIn(
            "#define AP01_AGENTS_WEATHER_SOLO_REQUEST 1u",
            endpoint_header,
        )

    def test_stock_https_untouched_keeps_https_call_original(self) -> None:
        if (
            not shutil.which("riscv64-elf-as")
            or not shutil.which("riscv64-elf-gcc")
        ):
            self.skipTest("本机没有阶段固件或固定编译工具")
        endpoints = (
            "http://10.0.0.10:18765/a",
            "http://10.0.0.11:18765/a",
        )
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            result = build_live_data_stock_https_untouched_firmware(
                self.stage,
                root / LIVE_DATA_STOCK_HTTPS_UNTOUCHED_OUTPUT_FILENAME,
                root / "manifest.json",
                root / "payload",
                endpoints=endpoints,
                endpoint_timeout_seconds=3,
                refresh_seconds=300,
                tool_revision={"commit": "test", "scoped_code_dirty": False},
            )
            document = json.loads(result.manifest.read_text(encoding="utf-8"))
            output_bytes = result.output.read_bytes()

        self.assertEqual(
            document["manifest_type"],
            "agents-stock-https-untouched-firmware",
        )
        self.assertTrue(document["validation"]["installation_allowed"])
        self.assertTrue(document["transport"]["weather_and_agents_dual_request"])
        self.assertFalse(document["transport"]["stock_https_network_call_patched"])
        self.assertTrue(
            document["transport"]["weather_success_requires_stock_weather_request"]
        )
        self.assertTrue(document["transport"]["weather_stock_first"])
        self.assertEqual(
            output_bytes[
                HTTPS_PERFORM_CALL :
                HTTPS_PERFORM_CALL + len(INSTRUCTION_EXPECTED[HTTPS_PERFORM_CALL])
            ],
            INSTRUCTION_EXPECTED[HTTPS_PERFORM_CALL],
        )
        self.assertNotEqual(
            output_bytes[
                HTTP_PERFORM_CALL :
                HTTP_PERFORM_CALL + len(INSTRUCTION_EXPECTED[HTTP_PERFORM_CALL])
            ],
            INSTRUCTION_EXPECTED[HTTP_PERFORM_CALL],
        )
        self.assertIsNone(document["callchain_gates"]["stock_https_webclient_call"])

    def test_post_weather_fetch_keeps_https_call_and_hooks_return(self) -> None:
        if (
            not shutil.which("riscv64-elf-as")
            or not shutil.which("riscv64-elf-gcc")
        ):
            self.skipTest("本机没有阶段固件或固定编译工具")
        endpoints = (
            "http://10.0.0.10:18765/a",
            "http://10.0.0.11:18765/a",
        )
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            result = build_live_data_post_weather_fetch_firmware(
                self.stage,
                root / LIVE_DATA_POST_WEATHER_FETCH_OUTPUT_FILENAME,
                root / "manifest.json",
                root / "payload",
                endpoints=endpoints,
                endpoint_timeout_seconds=3,
                refresh_seconds=300,
                tool_revision={"commit": "test", "scoped_code_dirty": False},
            )
            document = json.loads(result.manifest.read_text(encoding="utf-8"))
            output_bytes = result.output.read_bytes()
            endpoint_header = (root / "payload" / "endpoint-config.h").read_text(
                encoding="ascii"
            )
            disassembly = (
                root / "payload" / "agents-sync.disassembly.txt"
            ).read_text(encoding="utf-8")

        self.assertEqual(
            document["manifest_type"],
            "agents-post-weather-fetch-firmware",
        )
        self.assertTrue(document["validation"]["installation_allowed"])
        self.assertTrue(document["transport"]["post_weather_fetch_enabled"])
        self.assertFalse(document["transport"]["stock_https_network_call_patched"])
        self.assertTrue(document["transport"]["weather_stock_first"])
        self.assertEqual(
            output_bytes[
                HTTPS_PERFORM_CALL :
                HTTPS_PERFORM_CALL + len(INSTRUCTION_EXPECTED[HTTPS_PERFORM_CALL])
            ],
            INSTRUCTION_EXPECTED[HTTPS_PERFORM_CALL],
        )
        self.assertNotEqual(
            output_bytes[
                POST_WEATHER_FETCH_HOOK :
                POST_WEATHER_FETCH_HOOK + len(POST_WEATHER_FETCH_HOOK_ORIGINAL)
            ],
            POST_WEATHER_FETCH_HOOK_ORIGINAL,
        )
        self.assertNotEqual(
            output_bytes[
                POST_WEATHER_FETCH_TRAMPOLINE_OFFSET :
                POST_WEATHER_FETCH_TRAMPOLINE_OFFSET
                + len(POST_WEATHER_FETCH_TRAMPOLINE_ORIGINAL)
            ],
            POST_WEATHER_FETCH_TRAMPOLINE_ORIGINAL,
        )
        self.assertIsNone(document["callchain_gates"]["stock_https_webclient_call"])
        self.assertIsNotNone(document["callchain_gates"]["post_weather_fetch"])
        self.assertIn(
            "#define AP01_AGENTS_POST_WEATHER_FETCH 1u",
            endpoint_header,
        )
        self.assertIn("<ap01_agents_post_weather_fetch_entry>:", disassembly)

    def test_location_slot_dashboard_keeps_city_weather_and_https_original(self) -> None:
        if (
            not shutil.which("riscv64-elf-as")
            or not shutil.which("riscv64-elf-gcc")
        ):
            self.skipTest("本机没有阶段固件或固定编译工具")
        endpoints = (
            "http://10.0.0.10:18765/a",
            "http://10.0.0.11:18765/a",
        )
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            result = build_live_data_location_slot_dashboard_firmware(
                self.stage,
                root / LIVE_DATA_LOCATION_SLOT_DASHBOARD_OUTPUT_FILENAME,
                root / "manifest.json",
                root / "payload",
                endpoints=endpoints,
                endpoint_timeout_seconds=3,
                refresh_seconds=300,
                tool_revision={"commit": "test", "scoped_code_dirty": False},
            )
            document = json.loads(result.manifest.read_text(encoding="utf-8"))
            output_bytes = result.output.read_bytes()
            endpoint_header = (root / "payload" / "endpoint-config.h").read_text(
                encoding="ascii"
            )
            disassembly = (
                root / "payload" / "agents-sync.disassembly.txt"
            ).read_text(encoding="utf-8")

        self.assertEqual(
            document["manifest_type"],
            "agents-location-slot-dashboard-firmware",
        )
        self.assertEqual(document["status"], "approved-for-one-test-installation")
        self.assertTrue(document["validation"]["installation_allowed"])
        self.assertTrue(document["completeness"]["complete"])
        self.assertEqual(document["completeness"]["missing_items"], [])
        self.assertTrue(document["endpoint_personalization"]["supported"])
        self.assertFalse(
            document["endpoint_personalization"]["required_before_install"]
        )
        self.assertTrue(
            document["endpoint_personalization"]["multiple_addresses_supported"]
        )
        self.assertEqual(
            document["endpoint_personalization"]["current_endpoint_count"],
            len(endpoints),
        )
        self.assertTrue(document["transport"]["location_slot_dashboard_enabled"])
        self.assertFalse(document["transport"]["stock_https_network_call_patched"])
        self.assertFalse(document["transport"]["weather_and_agents_dual_request"])
        self.assertTrue(
            document["transport"]["stock_location_weather_slot_repurposed_for_dashboard"]
        )
        self.assertTrue(
            document["transport"]["stock_city_weather_request_regions_preserved"]
        )
        self.assertEqual(
            output_bytes[
                HTTPS_PERFORM_CALL :
                HTTPS_PERFORM_CALL + len(INSTRUCTION_EXPECTED[HTTPS_PERFORM_CALL])
            ],
            INSTRUCTION_EXPECTED[HTTPS_PERFORM_CALL],
        )
        self.assertNotEqual(
            output_bytes[
                HTTP_PERFORM_CALL :
                HTTP_PERFORM_CALL + len(INSTRUCTION_EXPECTED[HTTP_PERFORM_CALL])
            ],
            INSTRUCTION_EXPECTED[HTTP_PERFORM_CALL],
        )
        location_url_offset, location_url_capacity, _, _ = URL_REGIONS[0]
        location_format_offset, location_format_capacity, _, _ = URL_REGIONS[1]
        city_url_offset, city_url_capacity, city_url_original, _ = URL_REGIONS[2]
        city_format_offset, city_format_capacity, city_format_original, _ = URL_REGIONS[3]
        self.assertEqual(
            output_bytes[
                location_url_offset : location_url_offset + location_url_capacity
            ].rstrip(b"\0"),
            endpoints[0].encode("ascii"),
        )
        self.assertEqual(
            output_bytes[
                location_format_offset :
                location_format_offset + location_format_capacity
            ].rstrip(b"\0"),
            b"%s",
        )
        self.assertEqual(
            output_bytes[city_url_offset : city_url_offset + city_url_capacity],
            city_url_original.ljust(city_url_capacity, b"\0"),
        )
        self.assertEqual(
            output_bytes[
                city_format_offset : city_format_offset + city_format_capacity
            ],
            city_format_original.ljust(city_format_capacity, b"\0"),
        )
        self.assertIn(
            "#define AP01_AGENTS_LOCATION_SLOT_DASHBOARD 1u",
            endpoint_header,
        )
        location_block = disassembly.split(
            "<ap01_agents_location_stub>:", 1
        )[1].split("<ap01_agents_webclient_wrapper>:", 1)[0]
        self.assertIn("<fw_stock_weather_city_present>", location_block)
        self.assertNotIn("<fw_stock_location_lookup>", location_block)

    def test_rejected_weather_round_robin_cannot_be_rebuilt(self) -> None:
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            with self.assertRaisesRegex(
                AgentsDashboardFirmwareError,
                "FW-AGENTS-018",
            ):
                build_live_data_weather_round_robin_firmware(
                    self.stage,
                    root / LIVE_DATA_WEATHER_ROUND_ROBIN_OUTPUT_FILENAME,
                    root / "manifest.json",
                    root / "payload",
                    endpoints=(
                        "http://10.0.0.10:18765/a",
                        "http://10.0.0.11:18765/a",
                    ),
                    endpoint_timeout_seconds=3,
                    refresh_seconds=300,
                    tool_revision={"commit": "test", "scoped_code_dirty": False},
                )

    def test_failed_live_data_low_stack_name_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            with self.assertRaisesRegex(
                RuntimeError,
                "FW-AGENTS-013 已因安装后无设备取包请求停用",
            ):
                build_live_data_low_stack_firmware(
                    self.stage,
                    root / LIVE_DATA_LOW_STACK_OUTPUT_FILENAME,
                    root / "manifest.json",
                    root / "payload",
                    url_base="http://10.0.0.11:18765/a",
                    refresh_seconds=300,
                    tool_revision={
                        "commit": "test",
                        "scoped_code_dirty": False,
                    },
                )

    def test_failed_live_data_base_safe_name_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            with self.assertRaisesRegex(
                RuntimeError,
                "FW-AGENTS-011 已因安装后无设备取包请求停用",
            ):
                build_live_data_base_safe_firmware(
                    self.stage,
                    root / LIVE_DATA_BASE_SAFE_OUTPUT_FILENAME,
                    root / "manifest.json",
                    root / "payload",
                    url_base="http://10.0.0.11:18765/a",
                    refresh_seconds=300,
                    tool_revision={
                        "commit": "test",
                        "scoped_code_dirty": False,
                    },
                )

    def test_failed_reference_complete_name_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            with self.assertRaisesRegex(
                RuntimeError,
                "FW-AGENTS-012 已因安装后无设备取包请求停用",
            ):
                build_live_data_reference_complete_firmware(
                    self.stage,
                    root / LIVE_DATA_REFERENCE_COMPLETE_OUTPUT_FILENAME,
                    root / "manifest.json",
                    root / "payload",
                    url_base="http://10.0.0.11:18765/a",
                    refresh_seconds=300,
                    tool_revision={
                        "commit": "test",
                        "scoped_code_dirty": False,
                    },
                )

    def test_freestanding_crc32_matches_python(self) -> None:
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("本机没有主机 C 编译器")
        expected = zlib.crc32(b"abc") & 0xFFFFFFFF
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            harness = root / "harness.c"
            executable = root / "harness"
            harness.write_text(
                "\n".join(
                    (
                        "#define AP01_CRC_SELF_TEST 1",
                        "#include <stdio.h>",
                        (
                            "int ap01_agents_restore_pet(void *p) "
                            "{ (void)p; return 1; }"
                        ),
                        f'#include "{LOADER_SOURCE}"',
                        "int main(void) {",
                        '  const unsigned char input[] = "abc";',
                        "  unsigned int value = crc32_update(",
                        "      0xffffffffu, input, 3u) ^ 0xffffffffu;",
                        '  printf("%08x", value);',
                        "  return 0;",
                        "}",
                        "",
                    )
                ),
                encoding="utf-8",
            )
            build = subprocess.run(
                [compiler, "-O2", harness, "-o", executable],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            actual = subprocess.run(
                [executable],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
        self.assertEqual(actual, f"{expected:08x}")

    def test_streaming_loader_accepts_split_checked_package(self) -> None:
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("本机没有主机 C 编译器")
        page = _test_gif()
        package = encode_package(
            (page, page, page, page),
            generation=17,
            generated_at=1_700_000_000,
        )
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            harness = root / "loader-harness.c"
            executable = root / "loader-harness"
            package_values = ",".join(str(value) for value in package)
            harness.write_text(
                "\n".join(
                    (
                        "#define AP01_LOADER_SELF_TEST 1",
                        "#include <string.h>",
                        (
                            "int ap01_agents_restore_pet(void *p) "
                            "{ (void)p; return 1; }"
                        ),
                        "static unsigned char files[4][64];",
                        "static unsigned int sizes[4];",
                        "static int next_fd = 1;",
                        (
                            "int ap01_selftest_open(const char *p, int f, int m) "
                            "{ (void)p; (void)f; (void)m; return next_fd++; }"
                        ),
                        (
                            "int ap01_selftest_close(int fd) "
                            "{ return fd >= 1 && fd <= 4 ? 0 : -1; }"
                        ),
                        (
                            "int ap01_selftest_read(int fd, void *b, unsigned int n) "
                            "{ (void)fd; (void)b; (void)n; return -1; }"
                        ),
                        (
                            "int ap01_selftest_write(int fd, const void *b, "
                            "unsigned int n) { unsigned int i = (unsigned int)(fd - 1); "
                            "if (fd < 1 || fd > 4 || sizes[i] + n > 64) return -1; "
                            "memcpy(files[i] + sizes[i], b, n); sizes[i] += n; "
                            "return (int)n; }"
                        ),
                        "void *ap01_selftest_malloc(unsigned int n) "
                        "{ (void)n; return 0; }",
                        "void ap01_selftest_free(void *p) { (void)p; }",
                        "int ap01_selftest_webclient_perform(void *p) "
                        "{ (void)p; return -1; }",
                        f'#include "{LOADER_SOURCE}"',
                        f"static unsigned char package[] = {{{package_values}}};",
                        "int main(void) {",
                        "  struct download_state state;",
                        "  unsigned int offset = 0;",
                        "  unsigned int steps[] = {1, 7, 31, 3, 64, 2, 127, 11};",
                        "  unsigned int step = 0;",
                        "  memory_zero(&state, (unsigned int)sizeof(state));",
                        "  state.fd = -1;",
                        "  while (offset < (unsigned int)sizeof(package)) {",
                        "    unsigned int amount = steps[step++ % 8];",
                        "    char *cursor;",
                        "    int length;",
                        "    int result;",
                        "    if (amount > (unsigned int)sizeof(package) - offset)",
                        "      amount = (unsigned int)sizeof(package) - offset;",
                        "    cursor = (char *)package + offset;",
                        "    length = (int)amount;",
                        (
                            "    result = ap01_agents_sink(&cursor, 0, length, "
                            "&length, &state);"
                        ),
                        "    if (result != 0) return 10;",
                        "    offset += amount;",
                        "  }",
                        (
                            "  if (!state.complete || state.total != sizeof(package) "
                            "|| state.generation != 17 || next_fd != 5) return 11;"
                        ),
                        "  if (sizeof(state) != 136u) return 12;",
                        "  for (step = 0; step < 4; ++step)",
                        (
                            f"    if (sizes[step] != {len(page)} || "
                            "memcmp(files[step], package + PACKAGE_HEADER_SIZE "
                            f"+ step * {len(page)}, {len(page)}) != 0) return 13;"
                        ),
                        "  return 0;",
                        "}",
                        "",
                    )
                ),
                encoding="utf-8",
            )
            subprocess.run(
                [compiler, "-O2", harness, "-o", executable],
                check=True,
                capture_output=True,
                text=True,
            )
            result = subprocess.run(
                [executable],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_weather_stock_first_location_never_uses_placeholder(self) -> None:
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("本机没有主机 C 编译器")
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            harness = root / "weather-stock-first-harness.c"
            executable = root / "weather-stock-first-harness"
            harness.write_text(
                "\n".join(
                    (
                        "#define AP01_LOADER_SELF_TEST 1",
                        "#define AP01_AGENTS_WEATHER_COEXISTENCE 1u",
                        "#define AP01_AGENTS_WEATHER_DUAL_REQUEST 1u",
                        "#define AP01_AGENTS_WEATHER_SUCCESS_REQUIRES_STOCK 1u",
                        "#define AP01_AGENTS_STOCK_WEATHER_FIRST 1u",
                        "#include <string.h>",
                        "const unsigned char agents_fallback_overview_descriptor[] = {0};",
                        "const unsigned char agents_fallback_weekly_descriptor[] = {1};",
                        "const unsigned char agents_fallback_today_descriptor[] = {2};",
                        "const unsigned char agents_fallback_last_30_days_descriptor[] = {3};",
                        f'#include "{LOADER_SOURCE}"',
                        "static int stock_location_result;",
                        "static int stock_location_calls;",
                        "static int city_present;",
                        "int ap01_agents_restore_pet(void *p) { (void)p; return 1; }",
                        "void ap01_selftest_gif_set_src(void *gif, const void *source) { (void)gif; (void)source; }",
                        "int ap01_selftest_stock_location_lookup(void *target) {",
                        "  stock_location_calls += 1;",
                        "  if (stock_location_result) memcpy(target, \"123456789\", 10);",
                        "  return stock_location_result;",
                        "}",
                        "unsigned int ap01_selftest_weather_uptime_ms(void) { return 0; }",
                        "int ap01_selftest_weather_city_present(void) { return city_present; }",
                        "int ap01_selftest_open(const char *p, int f, int m) { (void)p; (void)f; (void)m; return -1; }",
                        "int ap01_selftest_close(int fd) { (void)fd; return 0; }",
                        "int ap01_selftest_read(int fd, void *b, unsigned int n) { (void)fd; (void)b; (void)n; return -1; }",
                        "int ap01_selftest_write(int fd, const void *b, unsigned int n) { (void)fd; (void)b; (void)n; return -1; }",
                        "void *ap01_selftest_malloc(unsigned int n) { (void)n; return 0; }",
                        "void ap01_selftest_free(void *p) { (void)p; }",
                        "int ap01_selftest_webclient_perform(void *context) { (void)context; return ERR_IO; }",
                        "int main(void) {",
                        "  unsigned char location[12];",
                        "  unsigned char untouched[10];",
                        "  memset(untouched, 0xaa, sizeof(untouched));",
                        "  memset(location, 0xaa, sizeof(location));",
                        "  agents_next_transport_mode = TRANSPORT_MODE_AGENTS_RETRY_WEATHER;",
                        "  stock_location_result = 1; city_present = 0;",
                        "  if (ap01_agents_location_stub(location) != 1) return 1;",
                        "  if (stock_location_calls != 1) return 2;",
                        "  if (memcmp(location, \"123456789\", 10) != 0) return 3;",
                        "  if (agents_transport_mode != TRANSPORT_MODE_WEATHER) return 4;",
                        "  if (agents_next_transport_mode != TRANSPORT_MODE_WEATHER) return 5;",
                        "  memset(location, 0xaa, sizeof(location));",
                        "  stock_location_result = 0; city_present = 1;",
                        "  if (ap01_agents_location_stub(location) != 0) return 6;",
                        "  if (memcmp(location, untouched, 10) != 0) return 7;",
                        "  if (agents_transport_mode != TRANSPORT_MODE_WEATHER) return 8;",
                        "  if (agents_next_transport_mode != TRANSPORT_MODE_WEATHER) return 9;",
                        "  memset(location, 0xaa, sizeof(location));",
                        "  city_present = 0;",
                        "  if (ap01_agents_location_stub(location) != 0) return 10;",
                        "  if (memcmp(location, untouched, 10) != 0) return 11;",
                        "  if (agents_transport_mode != TRANSPORT_MODE_WEATHER) return 12;",
                        "  if (agents_next_transport_mode != TRANSPORT_MODE_WEATHER) return 13;",
                        "  return 0;",
                        "}",
                        "",
                    )
                ),
                encoding="utf-8",
            )
            build = subprocess.run(
                [compiler, "-std=c99", "-Wall", "-Wextra", str(harness), "-o", str(executable)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            result = subprocess.run(
                [executable],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_streaming_loader_rejects_single_frame_with_embedded_marker(self) -> None:
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("本机没有主机 C 编译器")
        page = _test_gif(1, embedded_marker=True)
        package = encode_package(
            (page, page, page, page),
            generation=19,
            generated_at=1_700_000_000,
        )
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            harness = root / "single-frame-harness.c"
            executable = root / "single-frame-harness"
            package_values = ",".join(str(value) for value in package)
            harness.write_text(
                "\n".join(
                    (
                        "#define AP01_LOADER_SELF_TEST 1",
                        "int ap01_agents_restore_pet(void *p) "
                        "{ (void)p; return 1; }",
                        "static int next_fd = 1;",
                        "int ap01_selftest_open(const char *p, int f, int m) "
                        "{ (void)p; (void)f; (void)m; return next_fd++; }",
                        "int ap01_selftest_close(int fd) { return fd > 0 ? 0 : -1; }",
                        "int ap01_selftest_read(int fd, void *b, unsigned int n) "
                        "{ (void)fd; (void)b; (void)n; return -1; }",
                        "int ap01_selftest_write(int fd, const void *b, unsigned int n) "
                        "{ (void)fd; (void)b; return (int)n; }",
                        "void *ap01_selftest_malloc(unsigned int n) "
                        "{ (void)n; return 0; }",
                        "void ap01_selftest_free(void *p) { (void)p; }",
                        "int ap01_selftest_webclient_perform(void *p) "
                        "{ (void)p; return -1; }",
                        f'#include "{LOADER_SOURCE}"',
                        f"static unsigned char package[] = {{{package_values}}};",
                        "int main(void) {",
                        "  struct download_state state;",
                        "  char *cursor = (char *)package;",
                        "  int length = (int)sizeof(package);",
                        "  memory_zero(&state, (unsigned int)sizeof(state));",
                        "  state.fd = -1;",
                        "  if (ap01_agents_sink(&cursor, 0, length, &length, &state) "
                        "      != ERR_INVAL) return 10;",
                        "  if (state.complete != 0u) return 11;",
                        "  if (sizeof(state) != 136u) return 12;",
                        "  return 0;",
                        "}",
                        "",
                    )
                ),
                encoding="utf-8",
            )
            subprocess.run(
                [compiler, "-O2", harness, "-o", executable],
                check=True,
                capture_output=True,
                text=True,
            )
            result = subprocess.run(
                [executable],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_gif_parser_accepts_all_frozen_fallback_assets(self) -> None:
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("本机没有主机 C 编译器")
        assets = sorted(
            (REPO_ROOT / "features/agents_dashboard_firmware/assets").glob(
                "fallback-*.gif"
            )
        )
        self.assertEqual(len(assets), 4)
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            harness = root / "fallback-parser-harness.c"
            executable = root / "fallback-parser-harness"
            harness.write_text(
                "\n".join(
                    (
                        "#define AP01_CRC_SELF_TEST 1",
                        "#include <stdio.h>",
                        "int ap01_agents_restore_pet(void *p) "
                        "{ (void)p; return 1; }",
                        f'#include "{LOADER_SOURCE}"',
                        "int main(int argc, char **argv) {",
                        "  int file_index;",
                        "  if (argc != 5) return 9;",
                        "  for (file_index = 1; file_index < argc; ++file_index) {",
                        "    struct download_state state;",
                        "    FILE *stream = fopen(argv[file_index], \"rb\");",
                        "    unsigned int offset = 0u;",
                        "    int value;",
                        "    if (stream == 0) return 10;",
                        "    memory_zero(&state, (unsigned int)sizeof(state));",
                        "    while ((value = fgetc(stream)) != EOF) {",
                        "      if (gif_consume_byte(&state, offset++, (u8)value) != 0) "
                        "return 11;",
                        "    }",
                        "    if (fclose(stream) != 0) return 12;",
                        "    if (!gif_header_valid(state.gif_header)) return 13;",
                        "    if (gif_parse_state(&state) != GIF_STATE_DONE) return 14;",
                        "    if (gif_parse_frames(&state) < 2u) return 15;",
                        "  }",
                        "  return 0;",
                        "}",
                        "",
                    )
                ),
                encoding="utf-8",
            )
            subprocess.run(
                [compiler, "-O2", harness, "-o", executable],
                check=True,
                capture_output=True,
                text=True,
            )
            result = subprocess.run(
                [executable, *(str(asset) for asset in assets)],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_failed_wrapper_clears_all_files_in_unpublished_slot(self) -> None:
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("本机没有主机 C 编译器")
        page = _test_gif(1)
        package = encode_package(
            (page, page, page, page),
            generation=21,
            generated_at=1_700_000_000,
        )
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            harness = root / "cleanup-harness.c"
            executable = root / "cleanup-harness"
            package_values = ",".join(str(value) for value in package)
            harness.write_text(
                "\n".join(
                    (
                        "#define AP01_LOADER_SELF_TEST 1",
                        "#include <string.h>",
                        f'#include "{LOADER_SOURCE}"',
                        f"static unsigned char package[] = {{{package_values}}};",
                        "static unsigned char heap_state[136];",
                        "static int truncate_calls;",
                        "static int meta_writes;",
                        "static int next_fd = 1;",
                        "int ap01_agents_restore_pet(void *p) "
                        "{ (void)p; return 1; }",
                        "int ap01_selftest_open(const char *p, int f, int m) {",
                        "  (void)m;",
                        "  if (f == 39 && strstr(p, \".gif\") != 0) truncate_calls += 1;",
                        "  if (f == 39 && strstr(p, \".meta\") != 0) meta_writes += 1;",
                        "  return next_fd++;",
                        "}",
                        "int ap01_selftest_close(int fd) { return fd > 0 ? 0 : -1; }",
                        "int ap01_selftest_read(int fd, void *b, unsigned int n) "
                        "{ (void)fd; (void)b; (void)n; return -1; }",
                        "int ap01_selftest_write(int fd, const void *b, unsigned int n) "
                        "{ (void)fd; (void)b; return (int)n; }",
                        "void *ap01_selftest_malloc(unsigned int n) "
                        "{ return n == sizeof(heap_state) ? heap_state : 0; }",
                        "void ap01_selftest_free(void *p) { (void)p; }",
                        "int ap01_selftest_webclient_perform(void *context) {",
                        "  char *cursor = (char *)package;",
                        "  int length = (int)sizeof(package);",
                        "  void *state = *(void **)((unsigned char *)context + 64);",
                        "  *(unsigned int *)((unsigned char *)context + 96) = 200u;",
                        "  return ap01_agents_sink(&cursor, 0, length, &length, state);",
                        "}",
                        "int main(void) {",
                        "  unsigned char context[128];",
                        "  memset(context, 0, sizeof(context));",
                        "  if (ap01_agents_webclient_wrapper(context) != ERR_INVAL) return 10;",
                        "  if (truncate_calls != 5) return 11;",
                        "  if (meta_writes != 0) return 12;",
                        "  if (*(void **)(context + 64) != (void *)0) return 13;",
                        "  return 0;",
                        "}",
                        "",
                    )
                ),
                encoding="utf-8",
            )
            subprocess.run(
                [compiler, "-O2", harness, "-o", executable],
                check=True,
                capture_output=True,
                text=True,
            )
            result = subprocess.run(
                [executable],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_endpoint_wrapper_stops_on_success_and_fails_over_in_order(
        self,
    ) -> None:
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("本机没有主机 C 编译器")
        page = _test_gif()
        package = encode_package(
            (page, page, page, page),
            generation=24,
            generated_at=1_700_000_001,
        )
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            harness = root / "endpoint-wrapper-harness.c"
            executable = root / "endpoint-wrapper-harness"
            package_values = ",".join(str(value) for value in package)
            harness.write_text(
                "\n".join(
                    (
                        "#define AP01_LOADER_SELF_TEST 1",
                        "#define AP01_AGENTS_ENDPOINT_COUNT 10u",
                        "#define AP01_AGENTS_ENDPOINT_TIMEOUT_SECONDS 3u",
                        '#define AP01_AGENTS_ENDPOINT_1 "http://10.0.0.1:18765/a"',
                        '#define AP01_AGENTS_ENDPOINT_2 "http://10.0.0.2:18765/a"',
                        '#define AP01_AGENTS_ENDPOINT_3 "http://10.0.0.3:18765/a"',
                        '#define AP01_AGENTS_ENDPOINT_4 "http://10.0.0.4:18765/a"',
                        '#define AP01_AGENTS_ENDPOINT_5 "http://10.0.0.5:18765/a"',
                        '#define AP01_AGENTS_ENDPOINT_6 "http://10.0.0.6:18765/a"',
                        '#define AP01_AGENTS_ENDPOINT_7 "http://10.0.0.7:18765/a"',
                        '#define AP01_AGENTS_ENDPOINT_8 "http://10.0.0.8:18765/a"',
                        '#define AP01_AGENTS_ENDPOINT_9 "http://10.0.0.9:18765/a"',
                        '#define AP01_AGENTS_ENDPOINT_10 "http://10.0.0.10:18765/a"',
                        "#include <string.h>",
                        f'#include "{LOADER_SOURCE}"',
                        f"static unsigned char package[] = {{{package_values}}};",
                        "static unsigned char heap_state[136];",
                        "static int mode;",
                        "static int perform_calls;",
                        "static int free_calls;",
                        "static int next_fd = 1;",
                        "static const char *seen[10];",
                        "static const char *expected[10] = {",
                        "  AP01_AGENTS_ENDPOINT_1, AP01_AGENTS_ENDPOINT_2,",
                        "  AP01_AGENTS_ENDPOINT_3, AP01_AGENTS_ENDPOINT_4,",
                        "  AP01_AGENTS_ENDPOINT_5, AP01_AGENTS_ENDPOINT_6,",
                        "  AP01_AGENTS_ENDPOINT_7, AP01_AGENTS_ENDPOINT_8,",
                        "  AP01_AGENTS_ENDPOINT_9, AP01_AGENTS_ENDPOINT_10",
                        "};",
                        "int ap01_agents_restore_pet(void *p) "
                        "{ (void)p; return 1; }",
                        "int ap01_selftest_open(const char *p, int f, int m) "
                        "{ (void)p; (void)f; (void)m; return next_fd++; }",
                        "int ap01_selftest_close(int fd) "
                        "{ return fd > 0 ? 0 : -1; }",
                        "int ap01_selftest_read(int fd, void *b, unsigned int n) "
                        "{ (void)fd; (void)b; (void)n; return -1; }",
                        "int ap01_selftest_write(int fd, const void *b, "
                        "unsigned int n) { (void)fd; (void)b; return (int)n; }",
                        "void *ap01_selftest_malloc(unsigned int n) "
                        "{ return n == sizeof(heap_state) ? heap_state : 0; }",
                        "void ap01_selftest_free(void *p) "
                        "{ if (p == heap_state) free_calls += 1; }",
                        "int ap01_selftest_webclient_perform(void *context) {",
                        "  char *cursor = (char *)package;",
                        "  int length = (int)sizeof(package);",
                        "  void *state = *(void **)((unsigned char *)context + 64);",
                        "  seen[perform_calls] = *(const char **)((unsigned char *)context + 8);",
                        "  perform_calls += 1;",
                        "  if (perform_calls <= mode) return ERR_IO;",
                        "  *(unsigned int *)((unsigned char *)context + 96) = 200u;",
                        "  return ap01_agents_sink(&cursor, 0, length, &length, state);",
                        "}",
                        "static int run_case(unsigned char *context, int failures) {",
                        '  const char *original = "http://original/a";',
                        "  int index;",
                        "  memset(context, 0, 128);",
                        "  *(const char **)(context + 8) = original;",
                        "  *(unsigned int *)(context + 36) = 9u;",
                        "  *(void **)(context + 108) = (void *)1;",
                        "  mode = failures; perform_calls = 0;",
                        "  if (ap01_agents_webclient_wrapper(context) != 0) return 20;",
                        "  if (perform_calls != failures + 1) return 21;",
                        "  for (index = 0; index < perform_calls; ++index)",
                        "    if (strcmp(seen[index], expected[index]) != 0) return 22;",
                        "  if (*(const char **)(context + 8) != original) return 24;",
                        "  if (*(unsigned int *)(context + 36) != 9u) return 25;",
                        "  if (*(void **)(context + 64) != (void *)0) return 26;",
                        "  if (*(void **)(context + 108) != (void *)0) return 27;",
                        "  return 0;",
                        "}",
                        "int main(void) {",
                        "  unsigned char context[128];",
                        "  int result = run_case(context, 0);",
                        "  if (result != 0) return result;",
                        "  result = run_case(context, 9);",
                        "  if (result != 0) return result;",
                        "  if (free_calls != 2) return 28;",
                        "  return 0;",
                        "}",
                        "",
                    )
                ),
                encoding="utf-8",
            )
            build = subprocess.run(
                [compiler, "-O2", harness, "-o", executable],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            result = subprocess.run(
                [executable],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_low_stack_wrapper_allocates_and_releases_once(self) -> None:
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("本机没有主机 C 编译器")
        page = _test_gif()
        package = encode_package(
            (page, page, page, page),
            generation=23,
            generated_at=1_700_000_000,
        )
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            harness = root / "wrapper-harness.c"
            executable = root / "wrapper-harness"
            package_values = ",".join(str(value) for value in package)
            harness.write_text(
                "\n".join(
                    (
                        "#define AP01_LOADER_SELF_TEST 1",
                        "#include <string.h>",
                        f'#include "{LOADER_SOURCE}"',
                        f"static unsigned char package[] = {{{package_values}}};",
                        "static unsigned char heap_state[136];",
                        "static int fail_alloc = 1;",
                        "static int malloc_calls;",
                        "static int free_calls;",
                        "static int perform_calls;",
                        "static int next_fd = 1;",
                        "int ap01_agents_restore_pet(void *p) "
                        "{ (void)p; return 1; }",
                        "int ap01_selftest_open(const char *p, int f, int m) "
                        "{ (void)p; (void)f; (void)m; return next_fd++; }",
                        "int ap01_selftest_close(int fd) "
                        "{ return fd > 0 ? 0 : -1; }",
                        "int ap01_selftest_read(int fd, void *b, unsigned int n) "
                        "{ (void)fd; (void)b; (void)n; return -1; }",
                        "int ap01_selftest_write(int fd, const void *b, "
                        "unsigned int n) { (void)fd; (void)b; return (int)n; }",
                        "void *ap01_selftest_malloc(unsigned int n) {",
                        "  malloc_calls += 1;",
                        "  if (fail_alloc || n != sizeof(heap_state)) return 0;",
                        "  return heap_state;",
                        "}",
                        "void ap01_selftest_free(void *p) {",
                        "  if (p == heap_state) free_calls += 1;",
                        "}",
                        "int ap01_selftest_webclient_perform(void *context) {",
                        "  char *cursor = (char *)package;",
                        "  int length = (int)sizeof(package);",
                        "  void *state = *(void **)((unsigned char *)context + 64);",
                        "  perform_calls += 1;",
                        "  *(unsigned int *)((unsigned char *)context + 96) = 200u;",
                        "  return ap01_agents_sink(&cursor, 0, length, &length, state);",
                        "}",
                        "int main(void) {",
                        "  unsigned char context[128];",
                        "  unsigned char location[12];",
                        "  memset(context, 0, sizeof(context));",
                        "  memset(location, 0xaa, sizeof(location));",
                        "  if (ap01_agents_location_stub(0) != 0) return 8;",
                        "  if (ap01_agents_location_stub(location) != 1) return 9;",
                        "  if (memcmp(location, \"000000000\", 10) != 0) return 16;",
                        "  if (location[10] != 0xaa || location[11] != 0xaa) return 17;",
                        "  if (ap01_agents_webclient_wrapper(context) != ERR_IO) return 10;",
                        "  if (malloc_calls != 1 || free_calls != 0 || perform_calls != 0) return 11;",
                        "  fail_alloc = 0;",
                        "  if (ap01_agents_webclient_wrapper(context) != 0) return 12;",
                        "  if (malloc_calls != 2 || free_calls != 1 || perform_calls != 1) return 13;",
                        "  if (*(void **)(context + 64) != (void *)0) return 14;",
                        "  if (next_fd != 8) return 15;",
                        "  return 0;",
                        "}",
                        "",
                    )
                ),
                encoding="utf-8",
            )
            build = subprocess.run(
                [compiler, "-O2", harness, "-o", executable],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            result = subprocess.run(
                [executable],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_public_loader_never_calls_dashboard_network(self) -> None:
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("本机没有主机 C 编译器")
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            harness = root / "public-wrapper-harness.c"
            executable = root / "public-wrapper-harness"
            harness.write_text(
                "\n".join(
                    (
                        "#define AP01_LOADER_SELF_TEST 1",
                        "#define AP01_AGENTS_DISABLE_DOWNLOAD 1u",
                        "#include <string.h>",
                        f'#include "{LOADER_SOURCE}"',
                        "static int malloc_calls;",
                        "static int perform_calls;",
                        "int ap01_agents_restore_pet(void *p) "
                        "{ (void)p; return 1; }",
                        "int ap01_selftest_open(const char *p, int f, int m) "
                        "{ (void)p; (void)f; (void)m; return -1; }",
                        "int ap01_selftest_close(int fd) { (void)fd; return 0; }",
                        "int ap01_selftest_read(int fd, void *b, unsigned int n) "
                        "{ (void)fd; (void)b; (void)n; return -1; }",
                        "int ap01_selftest_write(int fd, const void *b, "
                        "unsigned int n) { (void)fd; (void)b; return (int)n; }",
                        "void *ap01_selftest_malloc(unsigned int n) "
                        "{ (void)n; malloc_calls += 1; return 0; }",
                        "void ap01_selftest_free(void *p) { (void)p; }",
                        "int ap01_selftest_webclient_perform(void *context) "
                        "{ (void)context; perform_calls += 1; return 0; }",
                        "int main(void) {",
                        "  unsigned char context[128];",
                        "  memset(context, 0, sizeof(context));",
                        "  if (ap01_agents_webclient_wrapper(context) != ERR_INVAL) return 10;",
                        "  if (malloc_calls != 0) return 11;",
                        "  if (perform_calls != 0) return 12;",
                        "  return 0;",
                        "}",
                        "",
                    )
                ),
                encoding="utf-8",
            )
            build = subprocess.run(
                [compiler, "-O2", harness, "-o", executable],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            result = subprocess.run(
                [executable],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_standalone_timer_host_self_test_covers_three_branches(self) -> None:
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("本机没有主机 C 编译器")
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            harness = root / "standalone-timer-harness.c"
            executable = root / "standalone-timer-harness"
            harness.write_text(
                "\n".join(
                    (
                        "#define AP01_LOADER_SELF_TEST 1",
                        "#define AP01_AGENTS_STANDALONE_TIMER 1u",
                        "#define AP01_AGENTS_REFRESH_SECONDS 300u",
                        "#define AP01_AGENTS_ENDPOINT_COUNT 1u",
                        "#define AP01_AGENTS_ENDPOINT_TIMEOUT_SECONDS 3u",
                        '#define AP01_AGENTS_ENDPOINT_1 "http://10.0.0.1:18765/a"',
                        "#include <string.h>",
                        f'#include "{LOADER_SOURCE}"',
                        "static unsigned char loop_storage[64];",
                        "static unsigned char timer_storage[0x58];",
                        "static unsigned char cb_context[116];",
                        "static unsigned char cb_buffer[4096];",
                        "static unsigned char download_state[136];",
                        "static int loop_ready = 1;",
                        "static int init_calls;",
                        "static int schedule_calls;",
                        "static unsigned int schedule_delays[8];",
                        "static int malloc_calls;",
                        "static int free_calls;",
                        "static int perform_calls;",
                        "static const char *perform_method_seen;",
                        "static const char *perform_url_seen;",
                        "static unsigned int perform_timeout_seen;",
                        "static unsigned int perform_buffer_size_seen;",
                        "static int perform_ready_seen;",
                        "static int perform_returns = -91;",
                        "int ap01_agents_restore_pet(void *p) "
                        "{ (void)p; return 1; }",
                        "int ap01_selftest_open(const char *p, int f, int m) "
                        "{ (void)p; (void)f; (void)m; return -1; }",
                        "int ap01_selftest_close(int fd) { (void)fd; return 0; }",
                        "int ap01_selftest_read(int fd, void *b, unsigned int n) "
                        "{ (void)fd; (void)b; (void)n; return -1; }",
                        "int ap01_selftest_write(int fd, const void *b, "
                        "unsigned int n) { (void)fd; (void)b; return (int)n; }",
                        "void *ap01_selftest_malloc(unsigned int n) {",
                        "  malloc_calls += 1;",
                        "  if (n == 116u) return cb_context;",
                        "  if (n == 4096u) return cb_buffer;",
                        "  if (n == 136u) return download_state;",
                        "  if (n == 0x58u) return timer_storage;",
                        "  return 0;",
                        "}",
                        "void ap01_selftest_free(void *p) "
                        "{ (void)p; free_calls += 1; }",
                        "int ap01_selftest_stock_timer_loop(void **loop) {",
                        "  if (!loop_ready) return -1;",
                        "  *loop = loop_storage;",
                        "  return 0;",
                        "}",
                        "void ap01_selftest_stock_timer_init(void *loop, void *timer) {",
                        "  unsigned char *handle = (unsigned char *)timer;",
                        "  unsigned char *node = handle + 0x10u;",
                        "  init_calls += 1;",
                        "  *(unsigned char **)(node + 4u) =",
                        "      *(unsigned char **)((unsigned char *)loop + 0x0cu);",
                        "  *(unsigned char **)((unsigned char *)loop + 0x0cu) = node;",
                        "  handle[8] = 0x0du;",
                        "}",
                        "int ap01_selftest_stock_timer_schedule(",
                        "    void *timer, void *callback, unsigned int delay_ms) {",
                        "  schedule_delays[schedule_calls] = delay_ms;",
                        "  schedule_calls += 1;",
                        "  *(void **)((unsigned char *)timer + 0x30u) = callback;",
                        "  return 0;",
                        "}",
                        "int ap01_selftest_webclient_perform(void *context) {",
                        "  unsigned char *block = (unsigned char *)context;",
                        "  perform_calls += 1;",
                        "  perform_method_seen = *(const char **)(block + 16);",
                        "  perform_url_seen = *(const char **)(block + 8);",
                        "  perform_timeout_seen = *(unsigned int *)(block + 36);",
                        "  perform_buffer_size_seen = *(unsigned int *)(block + 32);",
                        "  perform_ready_seen = block[40];",
                        "  return perform_returns;",
                        "}",
                        "int main(void) {",
                        "  unsigned char stock_context[116];",
                        "  unsigned char snapshot[116];",
                        "  /* 分支 1a：事件循环未就绪时不注册 */",
                        "  memset(loop_storage, 0, sizeof(loop_storage));",
                        "  loop_ready = 0;",
                        "  ap01_agents_standalone_timer_ensure();",
                        "  if (init_calls != 0 || schedule_calls != 0) return 1;",
                        "  if (malloc_calls != 0) return 2;",
                        "  /* 分支 1b：空链表时注册一次（首次延时 2000 毫秒） */",
                        "  loop_ready = 1;",
                        "  *(unsigned char **)(loop_storage + 0x0cu) = loop_storage + 8u;",
                        "  ap01_agents_standalone_timer_ensure();",
                        "  if (init_calls != 1 || schedule_calls != 1) return 3;",
                        "  if (schedule_delays[0] != 2000u) return 4;",
                        "  if (malloc_calls != 1) return 5;",
                        "  /* 分支 1c：第二次 ensure 探测到已注册节点，不重复注册 */",
                        "  ap01_agents_standalone_timer_ensure();",
                        "  if (init_calls != 1 || schedule_calls != 1) return 6;",
                        "  if (malloc_calls != 1) return 7;",
                        "  /* 分支 2：回调取包并按刷新周期再预约 */",
                        "  malloc_calls = 0; free_calls = 0; perform_calls = 0;",
                        "  schedule_calls = 0;",
                        "  ap01_agents_standalone_timer_cb(timer_storage);",
                        "  if (perform_calls != 1) return 8;",
                        "  if (strcmp(perform_method_seen, \"GET\") != 0) return 9;",
                        "  if (strcmp(perform_url_seen,",
                        "             AP01_AGENTS_ENDPOINT_1) != 0) return 10;",
                        "  if (perform_timeout_seen != 3u) return 11;",
                        "  if (perform_buffer_size_seen != 4096u) return 12;",
                        "  if (perform_ready_seen != 1) return 13;",
                        "  if (malloc_calls != 3 || free_calls != 3) return 14;",
                        "  if (schedule_calls != 1) return 15;",
                        "  if (schedule_delays[0] != 300000u) return 16;",
                        "  /* 分支 3：天气路径透传，原厂上下文零改动、返回值原样透传 */",
                        "  malloc_calls = 0; free_calls = 0; perform_calls = 0;",
                        "  memset(stock_context, 0xaa, sizeof(stock_context));",
                        "  *(const char **)(stock_context + 16) = \"POST\";",
                        "  *(const char **)(stock_context + 8) = \"http://stock/weather\";",
                        "  *(unsigned int *)(stock_context + 36) = 9u;",
                        "  memcpy(snapshot, stock_context, sizeof(snapshot));",
                        "  perform_returns = -77;",
                        "  if (ap01_agents_webclient_wrapper(stock_context) != -77) return 17;",
                        "  if (perform_calls != 1) return 18;",
                        "  if (strcmp(perform_url_seen, \"http://stock/weather\") != 0) return 19;",
                        "  if (perform_timeout_seen != 9u) return 20;",
                        "  if (memcmp(stock_context, snapshot, sizeof(stock_context)) != 0)",
                        "    return 21;",
                        "  if (malloc_calls != 0 || free_calls != 0) return 22;",
                        "  return 0;",
                        "}",
                        "",
                    )
                ),
                encoding="utf-8",
            )
            build = subprocess.run(
                [compiler, "-O2", harness, "-o", executable],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            result = subprocess.run(
                [executable],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_standalone_timer_firmware_decouples_dashboard_fetch_from_weather(
        self,
    ) -> None:
        if (
            not shutil.which("riscv64-elf-as")
            or not shutil.which("riscv64-elf-gcc")
        ):
            self.skipTest("本机没有阶段固件或固定编译工具")
        endpoints = ("http://10.0.0.1:18765/a",)
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            result = build_live_data_weather_hidden_dashboard_v2_firmware(
                self.stage,
                root / PERSONALIZED_FIRMWARE_OUTPUT_FILENAME,
                root / "manifest.json",
                root / "payload",
                endpoints=endpoints,
                endpoint_timeout_seconds=3,
                refresh_seconds=300,
                tool_revision={"commit": "test", "scoped_code_dirty": False},
                standalone_timer=True,
            )
            document = json.loads(result.manifest.read_text(encoding="utf-8"))
            disassembly = (
                root / "payload" / "agents-sync.disassembly.txt"
            ).read_text(encoding="utf-8")
            endpoint_header = (root / "payload" / "endpoint-config.h").read_text(
                encoding="ascii"
            )

        self.assertTrue(document["transport"]["standalone_timer_enabled"])
        self.assertEqual(
            document["transport"]["standalone_timer_refresh_seconds"], 300
        )
        self.assertIn("#define AP01_AGENTS_STANDALONE_TIMER 1u", endpoint_header)
        self.assertIn("#define AP01_AGENTS_REFRESH_SECONDS 300u", endpoint_header)
        self.assertIn(
            "看板取包由独立定时器按周期执行，与天气任务解耦",
            document["implemented_scope"],
        )
        self.assertIn(
            "原厂天气请求按原字节执行并原样返回",
            document["implemented_scope"],
        )
        self.assertNotIn(
            "天气网络执行后继续按地址优先级取得看板包",
            document["implemented_scope"],
        )
        self.assertIn("<ap01_agents_standalone_timer_cb>:", disassembly)
        self.assertIn("<ap01_agents_standalone_timer_ensure>:", disassembly)
        self.assertTrue(document["validation"]["installation_allowed"])
        self.assertEqual(
            document["transport"]["endpoint_priority"], list(endpoints)
        )

    def test_weather_solo_request_skips_agents_download_on_weather_path(self) -> None:
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("本机没有主机 C 编译器")
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            harness = root / "weather-solo-request-harness.c"
            executable = root / "weather-solo-request-harness"
            harness.write_text(
                "\n".join(
                    (
                        "#define AP01_LOADER_SELF_TEST 1",
                        "#define AP01_AGENTS_WEATHER_COEXISTENCE 1u",
                        "#define AP01_AGENTS_WEATHER_DUAL_REQUEST 1u",
                        "#define AP01_AGENTS_WEATHER_SUCCESS_REQUIRES_STOCK 1u",
                        "#define AP01_AGENTS_STOCK_WEATHER_FIRST 1u",
                        "#define AP01_AGENTS_WEATHER_SOLO_REQUEST 1u",
                        "#include <string.h>",
                        "const unsigned char agents_fallback_overview_descriptor[] = {0};",
                        "const unsigned char agents_fallback_weekly_descriptor[] = {1};",
                        "const unsigned char agents_fallback_today_descriptor[] = {2};",
                        "const unsigned char agents_fallback_last_30_days_descriptor[] = {3};",
                        f'#include "{LOADER_SOURCE}"',
                        "static void *stock_sink = (void *)0x1234;",
                        "static void *stock_arg = (void *)0x5678;",
                        "static int weather_calls;",
                        "static int agents_calls;",
                        "static int malloc_calls;",
                        "int ap01_agents_restore_pet(void *p) { (void)p; return 1; }",
                        "void ap01_selftest_gif_set_src(void *gif, const void *source) { (void)gif; (void)source; }",
                        "int ap01_selftest_stock_location_lookup(void *target) { memcpy(target, \"123456789\", 10); return 1; }",
                        "unsigned int ap01_selftest_weather_uptime_ms(void) { return 0; }",
                        "int ap01_selftest_weather_city_present(void) { return 1; }",
                        "int ap01_selftest_open(const char *p, int f, int m) { (void)p; (void)f; (void)m; return -1; }",
                        "int ap01_selftest_close(int fd) { (void)fd; return 0; }",
                        "int ap01_selftest_read(int fd, void *b, unsigned int n) { (void)fd; (void)b; (void)n; return -1; }",
                        "int ap01_selftest_write(int fd, const void *b, unsigned int n) { (void)fd; (void)b; (void)n; return -1; }",
                        "void *ap01_selftest_malloc(unsigned int n) { (void)n; malloc_calls += 1; return 0; }",
                        "void ap01_selftest_free(void *p) { (void)p; }",
                        "int ap01_selftest_webclient_perform(void *context) {",
                        "  void *sink = *(void **)((unsigned char *)context + WEBCLIENT_SINK_OFFSET);",
                        "  if (sink == stock_sink) {",
                        "    weather_calls += 1;",
                        "    *(unsigned int *)((unsigned char *)context + 96) = 204u;",
                        "    return 77;",
                        "  }",
                        "  if (sink == (void *)ap01_agents_sink) agents_calls += 1;",
                        "  return -91;",
                        "}",
                        "int main(void) {",
                        "  unsigned char context[128];",
                        "  memset(context, 0, sizeof(context));",
                        "  *(const char **)(context + 8) = \"https://weather/original\";",
                        "  *(unsigned int *)(context + 36) = 5u;",
                        "  *(void **)(context + WEBCLIENT_SINK_OFFSET) = stock_sink;",
                        "  *(void **)(context + 64) = stock_arg;",
                        "  agents_transport_mode = TRANSPORT_MODE_WEATHER;",
                        "  if (ap01_agents_webclient_wrapper(context) != 77) return 1;",
                        "  if (*(unsigned int *)(context + 96) != 204u) return 2;",
                        "  if (weather_calls != 1 || agents_calls != 0) return 3;",
                        "  if (malloc_calls != 0) return 4;",
                        "  if (*(void **)(context + WEBCLIENT_SINK_OFFSET) != stock_sink) return 5;",
                        "  if (*(void **)(context + 64) != stock_arg) return 6;",
                        "  return 0;",
                        "}",
                        "",
                    )
                ),
                encoding="utf-8",
            )
            subprocess.run(
                [compiler, "-O2", harness, "-o", executable],
                check=True,
                capture_output=True,
                text=True,
            )
            result = subprocess.run(
                [executable],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_weather_and_agents_results_are_isolated(self) -> None:
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("本机没有主机 C 编译器")
        page = _test_gif()
        package = encode_package(
            (page, page, page, page),
            generation=25,
            generated_at=1_700_000_002,
        )
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            harness = root / "weather-coexistence-harness.c"
            executable = root / "weather-coexistence-harness"
            package_values = ",".join(str(value) for value in package)
            harness.write_text(
                "\n".join(
                    (
                        "#define AP01_LOADER_SELF_TEST 1",
                        "#define AP01_AGENTS_WEATHER_COEXISTENCE 1u",
                        "#define AP01_AGENTS_WEATHER_DUAL_REQUEST 1u",
                        "#define AP01_AGENTS_WEATHER_SUCCESS_REQUIRES_STOCK 1u",
                        "#define AP01_AGENTS_RESULT_DIAGNOSTIC 1u",
                        "#define AP01_AGENTS_ENDPOINT_COUNT 2u",
                        "#define AP01_AGENTS_ENDPOINT_TIMEOUT_SECONDS 3u",
                        '#define AP01_AGENTS_ENDPOINT_1 "http://first/a"',
                        '#define AP01_AGENTS_ENDPOINT_2 "http://second/a"',
                        "#include <string.h>",
                        "const unsigned char agents_fallback_overview_descriptor[] = {0};",
                        "const unsigned char agents_fallback_weekly_descriptor[] = {1};",
                        "const unsigned char agents_fallback_today_descriptor[] = {2};",
                        "const unsigned char agents_fallback_last_30_days_descriptor[] = {3};",
                        f'#include "{LOADER_SOURCE}"',
                        f"static unsigned char package[] = {{{package_values}}};",
                        "static unsigned char heap_state[136];",
                        "static int heap_enabled = 1;",
                        "static int stock_location_result;",
                        "static int city_present;",
                        "static unsigned int uptime_ms;",
                        "static int weather_result;",
                        "static unsigned int weather_status;",
                        "static int fail_agents;",
                        "static int perform_calls;",
                        "static int weather_calls;",
                        "static int agents_calls;",
                        "static int stock_location_calls;",
                        "static int diagnostic_source_calls;",
                        "static const void *diagnostic_source;",
                        "static unsigned int diagnostic_stage_during_perform;",
                        "static int next_fd = 1;",
                        "static void *stock_sink = (void *)0x1234;",
                        "static void *stock_arg = (void *)0x5678;",
                        "int ap01_agents_restore_pet(void *p) "
                        "{ (void)p; return 1; }",
                        "void ap01_selftest_gif_set_src(void *gif, const void *source) "
                        "{ (void)gif; diagnostic_source_calls += 1; diagnostic_source = source; }",
                        "int ap01_selftest_stock_location_lookup(void *target) {",
                        "  stock_location_calls += 1;",
                        "  if (stock_location_result) memcpy(target, \"123456789\", 10);",
                        "  return stock_location_result;",
                        "}",
                        "unsigned int ap01_selftest_weather_uptime_ms(void) "
                        "{ return uptime_ms; }",
                        "int ap01_selftest_weather_city_present(void) "
                        "{ return city_present; }",
                        "int ap01_selftest_open(const char *p, int f, int m) "
                        "{ (void)p; (void)f; (void)m; return next_fd++; }",
                        "int ap01_selftest_close(int fd) "
                        "{ return fd > 0 ? 0 : -1; }",
                        "int ap01_selftest_read(int fd, void *b, unsigned int n) "
                        "{ (void)fd; (void)b; (void)n; return -1; }",
                        "int ap01_selftest_write(int fd, const void *b, "
                        "unsigned int n) { (void)fd; (void)b; return (int)n; }",
                        "void *ap01_selftest_malloc(unsigned int n) "
                        "{ return heap_enabled && n == sizeof(heap_state) ? heap_state : 0; }",
                        "void ap01_selftest_free(void *p) { (void)p; }",
                        "int ap01_selftest_webclient_perform(void *context) {",
                        "  const char *url = *(const char **)((unsigned char *)context + 8);",
                        "  void *sink = *(void **)((unsigned char *)context + WEBCLIENT_SINK_OFFSET);",
                        "  perform_calls += 1;",
                        "  if (sink == stock_sink) {",
                        "    weather_calls += 1;",
                        "    *(unsigned int *)((unsigned char *)context + 96) = weather_status;",
                        "    return weather_result;",
                        "  }",
                        "  if (sink != (void *)ap01_agents_sink) return -90;",
                        "  if (agents_calls == 0) diagnostic_stage_during_perform = agents_diagnostic_stage;",
                        "  agents_calls += 1;",
                        "  if (fail_agents == 1 || strcmp(url, AP01_AGENTS_ENDPOINT_1) == 0) "
                        "    return ERR_IO;",
                        "  if (fail_agents == 2) { *(unsigned int *)((unsigned char *)context + 96) = 503u; return 0; }",
                        "  if (fail_agents == 3) { *(unsigned int *)((unsigned char *)context + 96) = 200u; return 0; }",
                        "  {",
                        "    char *cursor = (char *)package;",
                        "    int length = (int)sizeof(package);",
                        "    void *state = *(void **)((unsigned char *)context + 64);",
                        "    *(unsigned int *)((unsigned char *)context + 96) = 200u;",
                        "    return ap01_agents_sink(&cursor, 0, length, &length, state);",
                        "  }",
                        "}",
                        "static void reset_context(unsigned char *context) {",
                        "  memset(context, 0, 128);",
                        "  *(const char **)(context + 8) = \"https://weather/original\";",
                        "  *(unsigned int *)(context + 36) = 5u;",
                        "  *(void **)(context + WEBCLIENT_SINK_OFFSET) = stock_sink;",
                        "  *(void **)(context + 64) = stock_arg;",
                        "  perform_calls = weather_calls = agents_calls = 0;",
                        "  fail_agents = 0; weather_result = 0; weather_status = 200u;",
                        "}",
                        "static int context_restored(unsigned char *context) {",
                        "  return strcmp(*(const char **)(context + 8), "
                        "\"https://weather/original\") == 0 &&",
                        "    *(unsigned int *)(context + 36) == 5u &&",
                        "    *(void **)(context + WEBCLIENT_SINK_OFFSET) == stock_sink &&",
                        "    *(void **)(context + 64) == stock_arg &&",
                        "    *(void **)(context + 108) == (void *)0;",
                        "}",
                        "int main(void) {",
                        "  unsigned char context[128]; unsigned char location[12]; unsigned char gif[128]; int result;",
                        "  memset(gif, 0, sizeof(gif)); *(void **)(gif + 0x5c) = gif;",
                        "  agents_diagnostic_show(gif);",
                        "  if (diagnostic_source_calls != 1 || diagnostic_source != agents_fallback_overview_descriptor) return 1;",
                        "  agents_diagnostic_show(gif);",
                        "  if (diagnostic_source_calls != 1) return 2;",
                        "  memset(location, 0xaa, sizeof(location));",
                        "  stock_location_result = 1; city_present = 0; uptime_ms = 0;",
                        "  if (ap01_agents_location_stub(location) != 1) return 10;",
                        "  if (agents_diagnostic_stage != 0u) return 9;",
                        "  if (agents_transport_mode != TRANSPORT_MODE_AGENTS_RETRY_WEATHER) return 11;",
                        "  if (memcmp(location, \"000000000\", 10) != 0) return 12;",
                        "  if (stock_location_calls != 0) return 13;",
                        "  reset_context(context);",
                        "  heap_enabled = 0;",
                        "  result = ap01_agents_webclient_wrapper(context);",
                        "  if (result != ERR_IO || agents_diagnostic_stage != 0u) return 8;",
                        "  heap_enabled = 1; reset_context(context);",
                        "  fail_agents = 1; result = ap01_agents_webclient_wrapper(context);",
                        "  if (result != ERR_IO || agents_diagnostic_stage != 0u) return 50;",
                        "  reset_context(context); fail_agents = 2;",
                        "  result = ap01_agents_webclient_wrapper(context);",
                        "  if (result != ERR_IO || agents_diagnostic_stage != 1u) return 51;",
                        "  reset_context(context); fail_agents = 3;",
                        "  result = ap01_agents_webclient_wrapper(context);",
                        "  if (result != ERR_IO || agents_diagnostic_stage != 2u) return 52;",
                        "  reset_context(context);",
                        "  result = ap01_agents_webclient_wrapper(context);",
                        "  if (agents_diagnostic_stage != 3u) return 7;",
                        "  if (diagnostic_stage_during_perform != 0u) return 5;",
                        "  agents_diagnostic_show(gif);",
                        "  if (diagnostic_source != agents_fallback_last_30_days_descriptor) return 6;",
                        "  if (result != ERR_IO) return 14;",
                        "  if (*(unsigned int *)(context + 96) != 0u) return 15;",
                        "  if (weather_calls != 0 || agents_calls != 2) return 16;",
                        "  if (!context_restored(context)) return 17;",
                        "  if (ap01_agents_location_stub(location) != 1) return 18;",
                        "  if (agents_transport_mode != TRANSPORT_MODE_WEATHER) return 19;",
                        "  if (memcmp(location, \"123456789\", 10) != 0) return 20;",
                        "  reset_context(context);",
                        "  result = ap01_agents_webclient_wrapper(context);",
                        "  if (result != 0 || *(unsigned int *)(context + 96) != 200u) return 21;",
                        "  if (weather_calls != 1 || agents_calls != 2) return 22;",
                        "  if (!context_restored(context)) return 23;",
                        "  agents_next_transport_mode = TRANSPORT_MODE_WEATHER;",
                        "  stock_location_result = 0; city_present = 1; uptime_ms = 100001u;",
                        "  if (ap01_agents_location_stub(location) != 0) return 30;",
                        "  if (agents_transport_mode != TRANSPORT_MODE_WEATHER) return 31;",
                        "  reset_context(context);",
                        "  result = ap01_agents_webclient_wrapper(context);",
                        "  if (result != 0 || weather_calls != 1 || agents_calls != 2) return 32;",
                        "  agents_next_transport_mode = TRANSPORT_MODE_WEATHER;",
                        "  stock_location_result = 0; city_present = 1; uptime_ms = 100000u;",
                        "  if (ap01_agents_location_stub(location) != 0) return 40;",
                        "  if (agents_transport_mode != TRANSPORT_MODE_WEATHER) return 41;",
                        "  reset_context(context);",
                        "  result = ap01_agents_webclient_wrapper(context);",
                        "  if (result != 0 || *(unsigned int *)(context + 96) != 200u) return 42;",
                        "  if (weather_calls != 1 || agents_calls != 2) return 43;",
                        "  if (!context_restored(context)) return 44;",
                        "  agents_next_transport_mode = TRANSPORT_MODE_WEATHER;",
                        "  stock_location_result = 0; city_present = 0; uptime_ms = 0;",
                        "  if (ap01_agents_location_stub(location) != 0) return 50;",
                        "  if (agents_transport_mode != TRANSPORT_MODE_WEATHER) return 51;",
                        "  reset_context(context);",
                        "  result = ap01_agents_webclient_wrapper(context);",
                        "  if (result != 0 || *(unsigned int *)(context + 96) != 200u) return 52;",
                        "  if (weather_calls != 1 || agents_calls != 2) return 53;",
                        "  reset_context(context);",
                        "  agents_transport_mode = TRANSPORT_MODE_AGENTS_ONLY;",
                        "  result = ap01_agents_webclient_wrapper(context);",
                        "  if (result != ERR_IO || *(unsigned int *)(context + 96) != 0u) return 54;",
                        "  if (weather_calls != 0 || agents_calls != 2) return 55;",
                        "  agents_next_transport_mode = TRANSPORT_MODE_WEATHER;",
                        "  stock_location_result = 1;",
                        "  if (ap01_agents_location_stub(location) != 1) return 60;",
                        "  reset_context(context); weather_result = ERR_IO; weather_status = 503u;",
                        "  result = ap01_agents_webclient_wrapper(context);",
                        "  if (result != ERR_IO || *(unsigned int *)(context + 96) != 503u) return 61;",
                        "  if (weather_calls != 1 || agents_calls != 2) return 62;",
                        "  agents_next_transport_mode = TRANSPORT_MODE_AGENTS_RETRY_WEATHER;",
                        "  if (ap01_agents_location_stub(location) != 1) return 70;",
                        "  reset_context(context); fail_agents = 1;",
                        "  result = ap01_agents_webclient_wrapper(context);",
                        "  if (result != ERR_IO || *(unsigned int *)(context + 96) != 0u) return 71;",
                        "  if (weather_calls != 0 || agents_calls != 2) return 72;",
                        "  if (!context_restored(context)) return 73;",
                        "  agents_next_transport_mode = TRANSPORT_MODE_AGENTS_RETRY_WEATHER;",
                        "  stock_location_result = 1; city_present = 0; uptime_ms = 0;",
                        "  { int round; for (round = 0; round < 6; ++round) {",
                        "    if (ap01_agents_location_stub(location) != 1) return 80;",
                        "    reset_context(context);",
                        "    result = ap01_agents_webclient_wrapper(context);",
                        "    if ((round & 1) == 0) {",
                        "      if (agents_transport_mode != TRANSPORT_MODE_AGENTS_RETRY_WEATHER ||",
                        "          result != ERR_IO || weather_calls != 0 || agents_calls != 2) return 81;",
                        "    } else {",
                        "      if (agents_transport_mode != TRANSPORT_MODE_WEATHER ||",
                        "          result != 0 || weather_calls != 1 || agents_calls != 2) return 82;",
                        "    }",
                        "  } }",
                        "  return 0;",
                        "}",
                        "",
                    )
                ),
                encoding="utf-8",
            )
            build = subprocess.run(
                [compiler, "-O2", harness, "-o", executable],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            result = subprocess.run(
                [executable],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
