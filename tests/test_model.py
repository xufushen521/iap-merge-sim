from __future__ import annotations

import unittest
from pathlib import Path
import sys


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from engine.loader import load_config, validate_config
from engine.model import RestaurantGame


class RestaurantGameTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config()
        self.game = RestaurantGame(self.config, seed=7)

    def test_generate_costs_energy_and_adds_item(self) -> None:
        initial_energy = self.game.energy
        initial_items = self.game.item_count
        self.assertTrue(self.game.generate("pantry"))
        self.assertEqual(self.game.energy, initial_energy - 3)
        self.assertEqual(self.game.item_count, initial_items + 1)

    def test_merge_same_items_creates_next_tier(self) -> None:
        game = RestaurantGame(self.config, seed=3)
        game.board = [None] * game.capacity
        game._add_item("coffee", 1, cell=0)
        game._add_item("coffee", 1, cell=1)
        self.assertTrue(game.merge(0, 1))
        self.assertIsNone(game.board[0])
        self.assertEqual(game.board[1].chain, "coffee")
        self.assertEqual(game.board[1].tier, 2)

    def test_merge_different_items_is_rejected(self) -> None:
        game = RestaurantGame(self.config, seed=4)
        game.board = [None] * game.capacity
        game._add_item("coffee", 1, cell=0)
        game._add_item("dessert", 1, cell=1)
        self.assertFalse(game.merge(0, 1))

    def test_max_tier_cannot_merge(self) -> None:
        game = RestaurantGame(self.config, seed=5)
        game.board = [None] * game.capacity
        max_tier = len(self.config["chains"]["coffee"]["items"])
        game._add_item("coffee", max_tier, cell=0)
        game._add_item("coffee", max_tier, cell=1)
        self.assertFalse(game.merge(0, 1))

    def test_complete_order_consumes_items_and_rewards(self) -> None:
        config = load_config()
        config["renovations"][0]["stars_required"] = 99
        game = RestaurantGame(config, seed=6)
        game.board = [None] * game.capacity
        order = game.active_orders[0]
        cell = 0
        for requirement in order.requirements:
            for _ in range(int(requirement["count"])):
                game._add_item(requirement["chain"], int(requirement["tier"]), cell=cell)
                cell += 1
        initial_coins = game.coins
        initial_stars = game.stars
        self.assertTrue(game.complete_order(0))
        self.assertTrue(all(item is None for item in game.board[:cell]))
        self.assertEqual(game.coins, initial_coins + order.reward["coins"])
        self.assertEqual(game.stars, initial_stars + order.reward["stars"])

    def test_renovation_consumes_coins_and_keeps_stars(self) -> None:
        game = RestaurantGame(self.config, seed=8)
        stage = game.next_renovation
        game.stars = int(stage["stars_required"])
        game.coins = float(stage["coins_required"]) + 10
        self.assertTrue(game.renovate_if_possible())
        self.assertEqual(game.stage_index, 1)
        self.assertEqual(game.coins, 10)
        self.assertEqual(game.stars, stage["stars_required"])

    def test_one_time_pack_cannot_repeat(self) -> None:
        self.game.apply_purchase("starter_pack")
        with self.assertRaises(ValueError):
            self.game.apply_purchase("starter_pack")

    def test_daily_energy_respects_cap(self) -> None:
        self.game.energy = float(self.config["economy"]["energy_cap"]) - 5
        gained = self.game.add_daily_energy(50)
        self.assertEqual(gained, 5)

    def test_same_seed_generates_same_starting_state(self) -> None:
        first = RestaurantGame(self.config, seed=11)
        second = RestaurantGame(self.config, seed=11)
        first_state = [
            None if item is None else (item.chain, item.tier)
            for item in first.board
        ]
        second_state = [
            None if item is None else (item.chain, item.tier)
            for item in second.board
        ]
        self.assertEqual(first_state, second_state)

    def test_segment_shares_must_sum_to_one(self) -> None:
        config = load_config()
        config["player_segments"][0]["share"] = 0.5
        with self.assertRaises(ValueError):
            validate_config(config)


if __name__ == "__main__":
    unittest.main()
