from __future__ import annotations

import unittest

from features.primary_page_settings.runtime_return_label import (
    simulate_page_settings_runtime_return_label,
)


class RuntimeReturnLabelTests(unittest.TestCase):
    def test_strict_simulation_covers_all_object_failure_paths(self) -> None:
        result = simulate_page_settings_runtime_return_label()
        self.assertTrue(result["passed"])
        self.assertEqual(result["contract"], "FW-PAGE-008-A")
        self.assertEqual(result["scenario_count"], 4)
        self.assertTrue(result["startup_call_unchanged"])
        self.assertFalse(result["press_entry_tested"])
        for scenario in result["scenarios"]:
            self.assertEqual(scenario["stock_create_calls"], 1)
            self.assertTrue(scenario["stock_return_preserved"])


if __name__ == "__main__":
    unittest.main()
