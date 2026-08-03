from __future__ import annotations

import io
import json
import stat
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

from .bridge import BridgeState
from .controlled_fault import (
    ControlledFaultError,
    ControlledFaultGate,
    arm_single_frame_fault,
)
from .result_package import decode_package, encode_package


def _gif(color: tuple[int, int, int]) -> bytes:
    first = Image.new("RGB", (320, 240), color)
    second = first.copy()
    second.putpixel((319, 239), ((color[0] + 1) % 256, color[1], color[2]))
    target = io.BytesIO()
    first.save(
        target,
        format="GIF",
        save_all=True,
        append_images=[second],
        duration=(1000, 1000),
        loop=0,
        optimize=True,
        disposal=2,
    )
    return target.getvalue()


class ControlledFaultTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pages = tuple(
            _gif(color)
            for color in (
                (0, 0, 0),
                (10, 20, 30),
                (40, 50, 60),
                (70, 80, 90),
            )
        )
        self.normal = encode_package(
            self.pages,
            generation=20,
            generated_at=1_700_000_000,
        )

    def _arm(
        self,
        root: Path,
        *,
        valid_seconds: int = 60,
        now: int = 1_700_000_100,
    ) -> Path:
        normal = root / "agents-dashboard.apag"
        normal.write_bytes(self.normal)
        plan = root / "single-frame-plan.json"
        arm_single_frame_fault(
            normal,
            plan,
            target_ip="192.168.31.231",
            valid_seconds=valid_seconds,
            now=now,
        )
        return plan

    def test_generated_fault_passes_package_checks_but_overview_is_single_frame(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = self._arm(root)
            document = json.loads(plan.read_text(encoding="utf-8"))
            fault_path = root / document["fault_package_name"]
            decoded = decode_package(fault_path.read_bytes())
            with Image.open(io.BytesIO(decoded.pages[0])) as overview:
                self.assertEqual(overview.size, (320, 240))
                self.assertEqual(overview.n_frames, 1)
            self.assertEqual(decoded.pages[1:], self.pages[1:])
            self.assertEqual(decoded.generation, 21)
            self.assertEqual(stat.S_IMODE(plan.stat().st_mode), 0o400)
            self.assertEqual(stat.S_IMODE(fault_path.stat().st_mode), 0o400)

    def test_matching_request_consumes_plan_before_returning_fault(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plan = self._arm(Path(directory))
            gate = ControlledFaultGate(plan)
            fault = gate.consume(
                "192.168.31.231", self.normal, now=1_700_000_110
            )
            self.assertIsNotNone(fault)
            self.assertFalse(plan.exists())
            self.assertTrue(Path(f"{plan}.consumed").is_file())
            self.assertTrue(gate.health()["controlled_fault_consumed"])

    def test_wrong_device_does_not_consume_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plan = self._arm(Path(directory))
            gate = ControlledFaultGate(plan)
            self.assertIsNone(
                gate.consume("192.168.31.99", self.normal, now=1_700_000_110)
            )
            self.assertTrue(plan.is_file())

    def test_changed_normal_package_does_not_consume_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plan = self._arm(Path(directory))
            gate = ControlledFaultGate(plan)
            self.assertIsNone(
                gate.consume(
                    "192.168.31.231", self.normal + b"x", now=1_700_000_110
                )
            )
            self.assertTrue(plan.is_file())

    def test_expired_plan_does_not_trigger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plan = self._arm(Path(directory), valid_seconds=10)
            gate = ControlledFaultGate(plan)
            self.assertIsNone(
                gate.consume("192.168.31.231", self.normal, now=1_700_000_111)
            )
            self.assertTrue(plan.is_file())

    def test_concurrent_requests_receive_exactly_one_fault(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plan = self._arm(Path(directory))
            gate = ControlledFaultGate(plan)
            with ThreadPoolExecutor(max_workers=8) as executor:
                results = list(
                    executor.map(
                        lambda _: gate.consume(
                            "192.168.31.231",
                            self.normal,
                            now=1_700_000_110,
                        ),
                        range(16),
                    )
                )
            self.assertEqual(sum(result is not None for result in results), 1)

    def test_consumed_plan_is_not_replayed_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plan = self._arm(Path(directory))
            first = ControlledFaultGate(plan)
            self.assertIsNotNone(
                first.consume("192.168.31.231", self.normal, now=1_700_000_110)
            )
            restarted = ControlledFaultGate(plan)
            self.assertIsNone(
                restarted.consume(
                    "192.168.31.231", self.normal, now=1_700_000_111
                )
            )
            health = restarted.health()
            self.assertTrue(health["controlled_fault_consumed"])
            self.assertIsNotNone(health["controlled_fault_last_trigger"])

    def test_expired_plan_is_not_reported_as_armed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plan = self._arm(Path(directory), valid_seconds=1)
            gate = ControlledFaultGate(plan)
            document = json.loads(plan.read_text(encoding="utf-8"))
            document["expires_at"] = 1
            plan.chmod(0o600)
            plan.write_text(json.dumps(document), encoding="utf-8")
            plan.chmod(0o400)
            self.assertFalse(gate.health()["controlled_fault_armed"])

    def test_bridge_defaults_to_normal_package_and_closed_fault_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "agents-dashboard.apag").write_bytes(self.normal)
            state = BridgeState(root, root)
            body, controlled = state.package_for_request("192.168.31.231")
            health = json.loads(state.health())
            self.assertEqual(body, self.normal)
            self.assertFalse(controlled)
            self.assertFalse(health["controlled_fault_enabled"])
            self.assertEqual(health["requests"], 1)

    def test_bridge_serves_fault_once_then_returns_to_normal_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = self._arm(root, now=int(time.time()))
            state = BridgeState(root, root, controlled_fault_plan=plan)
            first, first_controlled = state.package_for_request(
                "192.168.31.231"
            )
            second, second_controlled = state.package_for_request(
                "192.168.31.231"
            )
            health = json.loads(state.health())
            self.assertNotEqual(first, self.normal)
            self.assertTrue(first_controlled)
            self.assertEqual(second, self.normal)
            self.assertFalse(second_controlled)
            self.assertTrue(health["controlled_fault_consumed"])
            self.assertEqual(health["requests"], 2)

    def test_arm_rejects_more_than_fifteen_minutes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            normal = root / "agents-dashboard.apag"
            normal.write_bytes(self.normal)
            with self.assertRaisesRegex(ControlledFaultError, "900 秒"):
                arm_single_frame_fault(
                    normal,
                    root / "plan.json",
                    target_ip="192.168.31.231",
                    valid_seconds=901,
                    now=1_700_000_100,
                )


if __name__ == "__main__":
    unittest.main()
