from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from features.agents_dashboard_firmware.endpoint_config import (
    EndpointConfigError,
    load_endpoint_config,
)


class EndpointConfigTests(unittest.TestCase):
    def _write(self, content: str) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "agents-dashboard.env"
        path.write_text(content, encoding="utf-8")
        return path

    def test_loads_private_hosts_in_order_and_trims_spaces(self) -> None:
        config = load_endpoint_config(
            self._write(
                "AP01_AGENTS_HOSTS=10.0.0.10, 10.0.0.11 ,10.0.0.12\n"
                "AP01_AGENTS_PORT=18765\n"
            )
        )
        self.assertEqual(
            config.endpoints,
            (
                "http://10.0.0.10:18765/a",
                "http://10.0.0.11:18765/a",
                "http://10.0.0.12:18765/a",
            ),
        )

    def test_loads_one_private_host(self) -> None:
        config = load_endpoint_config(
            self._write(
                "AP01_AGENTS_HOSTS=10.0.0.10\n"
                "AP01_AGENTS_PORT=18765\n"
            )
        )
        self.assertEqual(config.hosts, ("10.0.0.10",))

    def test_loads_ten_private_hosts(self) -> None:
        hosts = ",".join(f"10.0.0.{index}" for index in range(1, 11))
        config = load_endpoint_config(
            self._write(
                f"AP01_AGENTS_HOSTS={hosts}\n"
                "AP01_AGENTS_PORT=18765\n"
            )
        )
        self.assertEqual(len(config.endpoints), 10)

    def test_rejects_missing_value(self) -> None:
        with self.assertRaisesRegex(EndpointConfigError, "没有填写完整"):
            load_endpoint_config(
                self._write(
                    "AP01_AGENTS_HOSTS=\n"
                    "AP01_AGENTS_PORT=18765\n"
                )
            )

    def test_rejects_public_host(self) -> None:
        with self.assertRaisesRegex(EndpointConfigError, "IPv4 局域网地址"):
            load_endpoint_config(
                self._write(
                    "AP01_AGENTS_HOSTS=8.8.8.8,10.0.0.11\n"
                    "AP01_AGENTS_PORT=18765\n"
                )
            )

    def test_rejects_duplicate_hosts(self) -> None:
        with self.assertRaisesRegex(EndpointConfigError, "不能重复"):
            load_endpoint_config(
                self._write(
                    "AP01_AGENTS_HOSTS=10.0.0.10,10.0.0.10\n"
                    "AP01_AGENTS_PORT=18765\n"
                )
            )

    def test_rejects_empty_host_item(self) -> None:
        with self.assertRaisesRegex(EndpointConfigError, "包含空项"):
            load_endpoint_config(
                self._write(
                    "AP01_AGENTS_HOSTS=10.0.0.10,,10.0.0.11\n"
                    "AP01_AGENTS_PORT=18765\n"
                )
            )

    def test_rejects_more_than_ten_hosts(self) -> None:
        hosts = ",".join(f"10.0.0.{index}" for index in range(1, 12))
        with self.assertRaisesRegex(EndpointConfigError, "最多填写 10 项"):
            load_endpoint_config(
                self._write(
                    f"AP01_AGENTS_HOSTS={hosts}\n"
                    "AP01_AGENTS_PORT=18765\n"
                )
            )

    def test_rejects_invalid_port(self) -> None:
        with self.assertRaisesRegex(EndpointConfigError, "1 至 65535"):
            load_endpoint_config(
                self._write(
                    "AP01_AGENTS_HOSTS=10.0.0.10,10.0.0.11\n"
                    "AP01_AGENTS_PORT=70000\n"
                )
            )


if __name__ == "__main__":
    unittest.main()
