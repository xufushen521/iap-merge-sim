from __future__ import annotations

import unittest
from pathlib import Path
import sys


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from engine.loader import load_config
from engine.simulator import simulate_cohort, simulate_player


class SimulatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config()

    def test_same_player_seed_is_reproducible(self) -> None:
        first = simulate_player(self.config, 3, seed=88)
        second = simulate_player(self.config, 3, seed=88)
        first.pop("events", None)
        second.pop("events", None)
        self.assertEqual(first, second)

    def test_non_payer_has_no_revenue(self) -> None:
        config = load_config()
        config["player_segments"] = [
            {
                "id": "all_non_payer",
                "name": "全非付费",
                "share": 1.0,
                "daily_budget": 0.0,
                "offer_buy_probability": 0.0,
            }
        ]
        result = simulate_player(config, 0, seed=1)
        self.assertEqual(result["purchases"], 0)
        self.assertEqual(result["iap_revenue_usd"], 0)

    def test_cohort_returns_requested_players(self) -> None:
        rows = simulate_cohort(self.config, players=7, seed=12)
        self.assertEqual(len(rows), 7)
        self.assertTrue(all(1 <= row["active_days"] <= 14 for row in rows))
        self.assertTrue(all(row["simulated_days"] == 14 for row in rows))

    def test_simulation_has_progression_metrics(self) -> None:
        result = simulate_player(self.config, 0, seed=9)
        self.assertIn("orders_completed", result)
        self.assertIn("merges", result)
        self.assertIn("stage_index", result)
        self.assertIn("energy_block_days", result)


if __name__ == "__main__":
    unittest.main()
