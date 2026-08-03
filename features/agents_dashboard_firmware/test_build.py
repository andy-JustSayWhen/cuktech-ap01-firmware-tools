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
    LOCATION_LOOKUP_CALL,
    LOCATION_TRAMPOLINE_OFFSET,
    LOCATION_TRAMPOLINE_ORIGINAL,
    LOADER_SOURCE,
    LOADER_TRAMPOLINE_OFFSET,
    LOADER_TRAMPOLINE_ORIGINAL,
    LIVE_DATA_BASE_SAFE_OUTPUT_FILENAME,
    LIVE_DATA_REFERENCE_COMPLETE_OUTPUT_FILENAME,
    LIVE_DATA_LOW_STACK_OUTPUT_FILENAME,
    LIVE_DATA_LOCATION_INDEPENDENT_OUTPUT_FILENAME,
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
    build_live_data_location_independent_firmware,
    build_sync_firmware,
    build_sync_payload,
    decode_agents_state,
    encode_agents_state,
    route_stock_local_branch,
    validate_stock_local_branch_routes,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
STAGE = REPO_ROOT / "artifacts/firmware/opt-setting.bin"


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
                    url_base="http://192.168.31.174:18765/a",
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
                    url_base="http://192.168.31.139:8765/a",
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
                    url_base="http://192.168.31.139:8765/a",
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
                    url_base="http://192.168.31.139:8765/a",
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
                    url_base="http://192.168.31.139:8765/a",
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
                url_base="http://192.168.31.174:18765/a",
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
            "http://192.168.31.174:18765/a",
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
                    url_base="http://192.168.31.174:18765/a",
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
                    url_base="http://192.168.31.174:18765/a",
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
                    url_base="http://192.168.31.174:18765/a",
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


if __name__ == "__main__":
    unittest.main()
