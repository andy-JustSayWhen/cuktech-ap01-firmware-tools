from __future__ import annotations

import hashlib
import hmac
import json
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

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
    INSTRUCTION_EXPECTED,
    LOADER_SOURCE,
    OPT_INTEGRATION_OUTPUT_FILENAME,
    OPT_PAGE_FILTER_HOOK,
    PET_STATE_SIZE_EXTENDED,
    PET_STATE_SIZE_OFFSET,
    PET_STATE_SIZE_ORIGINAL,
    STOCK_CALLCHAIN_OUTPUT_FILENAME,
    STOCK_ENTER_GATE_OUTPUT_FILENAME,
    STOCK_KEY_CALLBACK_RANGE,
    STOCK_LOCAL_BRANCH_HOOKS,
    STOCK_LOCAL_BRANCHES_OUTPUT_FILENAME,
    STOCK_POWER_CONFIRM_RANGE,
    UI_CALLBACK_ADDI,
    UI_CALLBACK_LUI,
    XIP_DELTA,
    _request_formats,
    build_stock_callchain_firmware,
    build_stock_enter_gate_firmware,
    build_stock_local_branches_firmware,
    build_sync_firmware,
    build_sync_payload,
    decode_agents_state,
    encode_agents_state,
    route_stock_callchain,
    route_stock_enter_gate,
    validate_stock_callchain_routes,
)
from features.primary_page_settings import (
    REQUIRED_SYMBOLS as PAGE_SETTINGS_SYMBOLS,
    apply_page_settings_patches,
    build_page_settings_objects,
)
from features.primary_page_settings.build import (
    MENU_LIMIT_EIGHT,
    MENU_LIMIT_OFFSET,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
STAGE = REPO_ROOT / "artifacts/firmware/opt-setting.bin"


@dataclass(frozen=True)
class TestCredentials:
    device_id: str
    access_token: str
    secret_key: bytes


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

    def test_sync_payload_fits_and_full_candidate_is_bounded(self) -> None:
        if (
            not shutil.which("riscv64-elf-as")
            or not shutil.which("riscv64-elf-gcc")
        ):
            self.skipTest("本机没有阶段固件或固定编译工具")
        credentials = TestCredentials(
            device_id="1234abcd",
            access_token="0123456789abcdef",
            secret_key=bytes(range(32)),
        )
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            payload = build_sync_payload(
                self.stage,
                root / "payload",
                credentials,
                tool_revision={"commit": "test", "scoped_code_dirty": False},
                reuse_stock_pet=True,
            )
            disassembly = subprocess.run(
                ["riscv64-elf-objdump", "-d", payload.elf],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            output = root / STOCK_LOCAL_BRANCHES_OUTPUT_FILENAME
            manifest = root / "manifest.json"
            result = build_stock_local_branches_firmware(
                self.stage,
                output,
                manifest,
                root / "firmware",
                credentials,
                url_base="http://192.168.31.139:8765/a",
                refresh_seconds=300,
                tool_revision={"commit": "test", "scoped_code_dirty": False},
            )
            manifest_text = manifest.read_text(encoding="utf-8")
            manifest_document = json.loads(manifest_text)
            output_bytes = output.read_bytes()

        self.assertLess(payload.size, 60_934)
        self.assertGreater(60_934 - payload.size, 20_000)
        self.assertLessEqual(payload.maximum_static_stack, 768)
        self.assertEqual(result.payload_size, payload.size)
        self.assertEqual(len(output_bytes), self.stage.stat().st_size)
        self.assertTrue(output_bytes.startswith(b"BFNP"))
        self.assertNotIn(credentials.access_token, manifest_text)
        self.assertNotIn(credentials.secret_key.hex(), manifest_text)
        self.assertIn('"installation_allowed": false', manifest_text)
        self.assertIn('"download_state_heap_bytes": 0', manifest_text)
        self.assertIn('"stock_pet_object_reused": true', manifest_text)
        self.assertEqual(
            payload.route_validation,
            {
                "dispatch_key_cases": 27,
                "gate_dispatch_key_cases": 27,
                "gate_stock_direct_cases": 14,
                "gate_wrapped_cases": 13,
                "detail_rotation_cases": 6,
                "invalid_tail_cases": 5,
                "valid_tail_cases": 5,
                "switch_failure_recovery_cases": 3,
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
                "four_local_branch_targets_verified"
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
            callchain_gates["route_validation"]["dispatch_key_cases"],
            27,
        )
        self.assertIn(
            "switch_failure_restore_call",
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
            "# a00b06f4 <window_set_active>",
            "# a007e1c4 <malloc>",
            "# a007c256 <free>",
        ):
            self.assertNotIn(forbidden, disassembly)
        key_event = disassembly.split("<ap01_agents_key_event>:", 1)[1].split(
            "<ap01_agents_stock_power_left_entry>:", 1
        )[0]
        self.assertIn("<ap01_agents_find_pet_state>", key_event)
        self.assertIn("<stock_get_dispatch_index>", key_event)
        self.assertIn("<stock_switch_page>", key_event)
        self.assertIn("<ap01_agents_stock_passthrough>", key_event)
        self.assertNotIn("52(s1)", key_event)
        self.assertNotIn("56(s1)", key_event)
        self.assertNotIn("60(s1)", key_event)
        self.assertIn("<stock_key_event>", key_event)
        fast_gate = disassembly.split(
            "<ap01_agents_key_event>:", 1
        )[1].split("<ap01_agents_wrapped_key_event>:", 1)[0]
        self.assertNotIn("addi\tsp", fast_gate)
        self.assertNotIn("sw\t", fast_gate)
        self.assertNotIn("call", fast_gate)
        self.assertIn("52(t1)", fast_gate)
        self.assertIn("<ap01_agents_fast_stock_passthrough>", fast_gate)
        self.assertGreaterEqual(
            fast_gate.count("<ap01_agents_wrapped_key_event>"),
            2,
        )
        self.assertNotIn("<ap01_agents_page_register>", fast_gate)
        fast_passthrough = disassembly.split(
            "<ap01_agents_fast_stock_passthrough>:", 1
        )[1].split("<ap01_agents_stock_power_left_entry>:", 1)[0]
        self.assertIn("<stock_key_event>", fast_passthrough)
        self.assertNotIn("lw\t", fast_passthrough)
        self.assertNotIn("sw\t", fast_passthrough)
        local_branches = disassembly.split(
            "<ap01_agents_stock_power_left_entry>:", 1
        )[1].split("<ap01_agents_show_page>:", 1)[0]
        for marker in (
            "<ap01_agents_find_pet_state>",
            "<ap01_agents_state_read>",
            "<ap01_agents_show_page>",
            "<ap01_agents_restore_pet>",
            "<stock_switch_page>",
            "<stock_power_left_resume>",
            "<stock_pet_left_resume>",
            "<stock_pet_right_resume>",
            "<stock_pet_enter_resume>",
            "<stock_key_epilogue>",
        ):
            self.assertIn(marker, local_branches)
        self.assertNotIn("<stock_key_event>", local_branches)
        state_write = disassembly.split(
            "<ap01_agents_state_write>:", 1
        )[1].split("<ap01_agents_find_pet_state>:", 1)[0]
        self.assertIn("16(a0)", state_write)
        for offset in (0, 4, 8, 12):
            self.assertNotIn(f"{offset}(a0)", state_write)
        find_state = disassembly.split("<ap01_agents_find_pet_state>:", 1)[1].split(
            "<ap01_agents_key_event>:", 1
        )[0]
        self.assertIn("li\ta1,7", find_state)
        self.assertIn("# a00be3ca <stock_get_child>", find_state)
        self.assertIn("16(a0)", find_state)
        self.assertIn("4(t0)", find_state)

    def test_stock_callchain_routes_all_dispatch_key_pairs(self) -> None:
        report = validate_stock_callchain_routes()
        self.assertEqual(report["dispatch_key_cases"], 27)
        self.assertEqual(report["gate_dispatch_key_cases"], 27)
        self.assertEqual(report["gate_stock_direct_cases"], 14)
        self.assertEqual(report["gate_wrapped_cases"], 13)
        for dispatch in (1, 2, 8):
            for key in (19, 20, 10):
                self.assertEqual(
                    route_stock_callchain(dispatch, key, 1).action,
                    "stock-callback",
                )
                self.assertEqual(
                    route_stock_enter_gate(dispatch, key),
                    "stock-direct",
                )
        for dispatch in (0, 3, 4, 5, 6):
            self.assertEqual(
                route_stock_callchain(dispatch, 10, 1).action,
                "stock-callback",
            )
            self.assertEqual(
                route_stock_enter_gate(dispatch, 10),
                "stock-direct",
            )
        self.assertEqual(route_stock_enter_gate(7, 10), "wrapped")
        self.assertEqual(
            route_stock_callchain(7, 10, 1).target_state,
            2,
        )
        for state in (2, 3, 4):
            self.assertEqual(
                route_stock_callchain(7, 10, state).target_state,
                1,
            )
        self.assertEqual(
            route_stock_callchain(7, 19, None).target_dispatch,
            6,
        )
        self.assertEqual(
            route_stock_callchain(7, 20, None).target_state,
            1,
        )

    def test_full_integration_candidate_uses_local_page_filter(self) -> None:
        assembler = shutil.which("riscv64-elf-as")
        compiler = shutil.which("riscv64-elf-gcc")
        if not assembler or not compiler:
            self.skipTest("本机没有固定编译工具")
        credentials = TestCredentials(
            device_id="1234abcd",
            access_token="0123456789abcdef",
            secret_key=bytes(range(32)),
        )
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            settings = build_page_settings_objects(
                root / "page-settings",
                REPO_ROOT / "env/fonts",
                assembler=Path(assembler),
                compiler=Path(compiler),
            )
            output = root / OPT_INTEGRATION_OUTPUT_FILENAME
            manifest = root / "manifest.json"
            result = build_sync_firmware(
                self.stage,
                output,
                manifest,
                root / "firmware",
                credentials,
                url_base="http://192.168.31.139:8765/a",
                refresh_seconds=300,
                tool_revision={"commit": "test", "scoped_code_dirty": False},
                extra_objects=settings.objects,
                required_extra_symbols=PAGE_SETTINGS_SYMBOLS,
                candidate_mutators=(apply_page_settings_patches,),
                expected_output_name=OPT_INTEGRATION_OUTPUT_FILENAME,
                implemented_scope_extra=("一级导航跳过关闭页面",),
                reuse_stock_pet=True,
            )
            document = json.loads(manifest.read_text(encoding="utf-8"))
            output_bytes = output.read_bytes()
            elf = root / "firmware/agents-sync.elf"
            disassembly = subprocess.run(
                ["riscv64-elf-objdump", "-d", elf],
                check=True,
                capture_output=True,
                text=True,
            ).stdout

        self.assertEqual(
            document["manifest_type"],
            "opt-integration-candidate-firmware",
        )
        self.assertEqual(
            document["status"],
            "built-not-approved-for-installation",
        )
        self.assertFalse(document["validation"]["installation_allowed"])
        self.assertTrue(
            document["validation"]["page_filter_switch_call_verified"]
        )
        self.assertEqual(len(document["callchain_gates"]["local_branch_hooks"]), 5)
        self.assertEqual(result.sha256, document["output"]["sha256"])
        self.assertEqual(
            output_bytes[MENU_LIMIT_OFFSET : MENU_LIMIT_OFFSET + 2],
            MENU_LIMIT_EIGHT,
        )
        (
            hook_offset,
            hook_original,
            trampoline_offset,
            symbol,
            _resume_address,
            _label,
        ) = OPT_PAGE_FILTER_HOOK
        self.assertEqual(
            output_bytes[hook_offset : hook_offset + len(hook_original)],
            _encode_jal(
                XIP_DELTA + hook_offset,
                XIP_DELTA + trampoline_offset,
            ),
        )
        self.assertIn(f"<{symbol}>:", disassembly)
        self.assertIn("<ap01_page_settings_load_mask>", disassembly)
        self.assertIn("<stock_switch_page>", disassembly)

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
        credentials = TestCredentials(
            device_id="1234abcd",
            access_token="0123456789abcdef",
            secret_key=bytes(range(32)),
        )
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            retired = "ap01-1.0.2_0031-agents-stock-dispatch-observation.bin"
            with self.assertRaisesRegex(
                RuntimeError,
                "旧 AGENTS 固件路径已停用",
            ):
                build_sync_firmware(
                    self.stage,
                    root / retired,
                    root / "manifest.json",
                    root / "build",
                    credentials,
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
                    credentials,
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
                    credentials,
                    url_base="http://192.168.31.139:8765/a",
                    refresh_seconds=300,
                    tool_revision={
                        "commit": "test",
                        "scoped_code_dirty": False,
                    },
                )

    def test_request_formats_fit_without_positional_printf(self) -> None:
        credentials = TestCredentials(
            device_id="1234abcd",
            access_token="0123456789abcdef",
            secret_key=bytes(range(32)),
        )
        location, city = _request_formats(credentials)
        self.assertLessEqual(len(location) + 1, 44)
        self.assertLessEqual(len(city) + 1, 48)
        self.assertNotIn(b"$", location)
        self.assertNotIn(b"$", city)
        self.assertIn(b"d=abcd", location)
        self.assertIn(b"t=456789abcdef", location)

    def test_freestanding_hmac_matches_python(self) -> None:
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("本机没有主机 C 编译器")
        secret = bytes(range(32))
        expected = hmac.new(secret, b"abc", hashlib.sha256).hexdigest()
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            harness = root / "harness.c"
            executable = root / "harness"
            secret_values = ",".join(str(value) for value in secret)
            harness.write_text(
                "\n".join(
                    (
                        "#define AP01_CRYPTO_SELF_TEST 1",
                        "const unsigned char agents_device_id[16] = {0};",
                        (
                            "const unsigned char agents_secret_key[32] = "
                            f"{{{secret_values}}};"
                        ),
                        (
                            "int ap01_agents_restore_pet(void *p) "
                            "{ (void)p; return 1; }"
                        ),
                        f'#include "{LOADER_SOURCE}"',
                        "#include <stdio.h>",
                        "int main(void) {",
                        "  unsigned char output[32];",
                        '  const unsigned char input[] = "abc";',
                        "  unsigned int index;",
                        "  ap01_agents_crypto_self_test(input, 3, output);",
                        "  for (index = 0; index < 32; ++index)",
                        '    printf("%02x", output[index]);',
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
            actual = subprocess.run(
                [executable],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
        self.assertEqual(actual, expected)

    def test_streaming_loader_accepts_split_authenticated_package(self) -> None:
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("本机没有主机 C 编译器")
        credentials = TestCredentials(
            device_id="1234abcd",
            access_token="0123456789abcdef",
            secret_key=bytes(range(32)),
        )
        page = b"GIF89a\x40\x01\xf0\x00\x00\x00\x3b"
        package = encode_package(
            (page, page, page, page),
            generation=17,
            generated_at=1_700_000_000,
            credentials=credentials,
        )
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            harness = root / "loader-harness.c"
            executable = root / "loader-harness"
            secret_values = ",".join(str(value) for value in credentials.secret_key)
            device_values = ",".join(
                str(value)
                for value in credentials.device_id.encode("ascii").ljust(16, b"\0")
            )
            package_values = ",".join(str(value) for value in package)
            harness.write_text(
                "\n".join(
                    (
                        "#define AP01_LOADER_SELF_TEST 1",
                        "#include <string.h>",
                        f"const unsigned char agents_device_id[16] = {{{device_values}}};",
                        (
                            "const unsigned char agents_secret_key[32] = "
                            f"{{{secret_values}}};"
                        ),
                        (
                            "int ap01_agents_restore_pet(void *p) "
                            "{ (void)p; return 1; }"
                        ),
                        "static unsigned char files[4][32];",
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
                            "if (fd < 1 || fd > 4 || sizes[i] + n > 32) return -1; "
                            "memcpy(files[i] + sizes[i], b, n); sizes[i] += n; "
                            "return (int)n; }"
                        ),
                        f'#include "{LOADER_SOURCE}"',
                        f"static unsigned char package[] = {{{package_values}}};",
                        "int main(void) {",
                        "  struct download_state state;",
                        "  unsigned int offset = 0;",
                        "  unsigned int steps[] = {1, 7, 31, 3, 64, 2, 127, 11};",
                        "  unsigned int step = 0;",
                        "  unsigned char actual_hmac[32];",
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
                        "  hmac_final(&state.hmac_inner, actual_hmac);",
                        (
                            "  if (!bytes_equal(actual_hmac, "
                            "state.header + PACKAGE_HMAC_OFFSET, 32)) return 12;"
                        ),
                        "  for (step = 0; step < 4; ++step)",
                        (
                            "    if (sizes[step] != 13 || "
                            "memcmp(files[step], package + PACKAGE_HEADER_SIZE "
                            "+ step * 13, 13) != 0) return 13;"
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


if __name__ == "__main__":
    unittest.main()
