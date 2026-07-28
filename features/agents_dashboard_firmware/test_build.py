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

from features.agents_dashboard.result_package import encode_package
from features.agents_dashboard_firmware import (
    build_observation_firmware,
    build_page_registration_payload,
)
from features.agents_dashboard_firmware.build import OBSERVATION_OUTPUT_FILENAME
from features.agents_dashboard_firmware.build import (
    HOOK_OFFSET,
    HOOK_ORIGINAL,
    TRAMPOLINE_OFFSET,
    TRAMPOLINE_ORIGINAL,
)
from features.agents_dashboard_firmware.sync_build import (
    LOADER_SOURCE,
    PET_STATE_SIZE_EXTENDED,
    PET_STATE_SIZE_OFFSET,
    PET_STATE_SIZE_ORIGINAL,
    STOCK_CALLCHAIN_OUTPUT_FILENAME,
    _request_formats,
    build_stock_callchain_firmware,
    build_sync_firmware,
    build_sync_payload,
    decode_agents_state,
    encode_agents_state,
    route_stock_callchain,
    validate_stock_callchain_routes,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
STAGE = REPO_ROOT / "artifacts/firmware/opt-setting.bin"


@dataclass(frozen=True)
class TestCredentials:
    device_id: str
    access_token: str
    secret_key: bytes


class AgentsDashboardFirmwareTests(unittest.TestCase):
    def test_real_stage_builds_linked_page_registration_payload(self) -> None:
        if not STAGE.is_file() or not shutil.which("riscv64-elf-as"):
            self.skipTest("本机没有阶段固件或固定编译工具")
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            document = build_page_registration_payload(
                STAGE,
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
        if not STAGE.is_file() or not shutil.which("riscv64-elf-as"):
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
                    STAGE,
                    output,
                    manifest,
                    root / "build",
                    tool_revision={"commit": "test", "scoped_code_dirty": False},
                )

    def test_sync_payload_fits_and_full_candidate_is_bounded(self) -> None:
        if (
            not STAGE.is_file()
            or not shutil.which("riscv64-elf-as")
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
                STAGE,
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
            output = root / STOCK_CALLCHAIN_OUTPUT_FILENAME
            manifest = root / "manifest.json"
            result = build_stock_callchain_firmware(
                STAGE,
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
        self.assertEqual(len(output_bytes), STAGE.stat().st_size)
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
        stage_bytes = STAGE.read_bytes()
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
            "<ap01_agents_show_page>:", 1
        )[0]
        self.assertIn("<ap01_agents_find_pet_state>", key_event)
        self.assertIn("<stock_get_dispatch_index>", key_event)
        self.assertIn("<stock_switch_page>", key_event)
        self.assertIn("<ap01_agents_stock_passthrough>", key_event)
        self.assertNotIn("52(s1)", key_event)
        self.assertNotIn("56(s1)", key_event)
        self.assertNotIn("60(s1)", key_event)
        self.assertIn("<stock_key_event>", key_event)
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
        for dispatch in (1, 2, 8):
            for key in (19, 20, 10):
                self.assertEqual(
                    route_stock_callchain(dispatch, key, 1).action,
                    "stock-callback",
                )
        for dispatch in (0, 3, 4, 5, 6):
            self.assertEqual(
                route_stock_callchain(dispatch, 10, 1).action,
                "stock-callback",
            )
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
                    STAGE,
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
