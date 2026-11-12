from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Item:
    uid: int
    chain: str
    tier: int
    name: str
    glyph: str


@dataclass
class ActiveOrder:
    order_key: int
    template_id: str
    title: str
    requirements: list[dict[str, Any]]
    reward: dict[str, int]


@dataclass
class Purchase:
    pack_id: str
    name: str
    price_usd: float
    day: int
    grants: dict[str, int] = field(default_factory=dict)


class RestaurantGame:
    def __init__(
        self,
        config: dict[str, Any],
        seed: int,
        starting_energy: float | None = None,
        starting_coins: float | None = None,
        starting_gems: float | None = None,
        record_events: bool = True,
    ) -> None:
        self.config = config
        self.seed = int(seed)
        self.rng = random.Random(seed)
        self.rows = int(config["board"]["rows"])
        self.cols = int(config["board"]["cols"])
        self.capacity = self.rows * self.cols
        self.board: list[Item | None] = [None] * self.capacity
        self.energy = float(
            config["economy"]["starting_energy"]
            if starting_energy is None
            else starting_energy
        )
        self.coins = float(
            config["economy"]["starting_coins"] if starting_coins is None else starting_coins
        )
        self.gems = float(
            config["economy"]["starting_gems"] if starting_gems is None else starting_gems
        )
        self.stars = 0
        self.stage_index = 0
        self.day = 1
        self.generator_uses = {
            generator["id"]: int(generator["daily_uses"])
            for generator in config["generators"]
        }
        self.purchases: list[Purchase] = []
        self._purchased_one_time: set[str] = set()
        self._next_uid = 1
        self._next_order_key = 1
        self._order_cursor = 0
        self.active_orders: list[ActiveOrder] = []
        self.events: list[dict[str, Any]] = []
        self._event_seq = 0
        self.record_events = record_events
        self.stats: dict[str, Any] = {
            "generations": 0,
            "merges": 0,
            "orders_completed": 0,
            "stages_completed": 0,
            "energy_spent": 0.0,
            "energy_gained": 0.0,
            "coins_earned": 0.0,
            "coins_spent": 0.0,
            "stars_earned": 0,
            "board_full_attempts": 0,
            "energy_blocked_attempts": 0,
            "iap_offers": 0,
            "purchases": 0,
            "iap_revenue_usd": 0.0,
        }
        for item in config["starting_items"]:
            self._add_item(item["chain"], int(item["tier"]))
        for _ in range(3):
            self.active_orders.append(self._draw_order())
        self._log("game_start")

    def _log(self, event_type: str, **payload: Any) -> None:
        if not self.record_events:
            return
        self._event_seq += 1
        event = {
            "event_seq": self._event_seq,
            "game_id": f"R{self.seed}",
            "day": self.day,
            "event_type": event_type,
            "energy": round(self.energy, 2),
            "coins": round(self.coins, 2),
            "gems": round(self.gems, 2),
            "stars": self.stars,
            "stage_index": self.stage_index,
            "board_items": self.item_count,
        }
        event.update(payload)
        self.events.append(event)

    @property
    def item_count(self) -> int:
        return sum(1 for item in self.board if item is not None)

    @property
    def free_cells(self) -> list[int]:
        return [index for index, item in enumerate(self.board) if item is None]

    @property
    def next_renovation(self) -> dict[str, Any] | None:
        if self.stage_index >= len(self.config["renovations"]):
            return None
        return self.config["renovations"][self.stage_index]

    def item_definition(self, chain: str, tier: int) -> dict[str, Any]:
        for item in self.config["chains"][chain]["items"]:
            if int(item["tier"]) == int(tier):
                return item
        raise KeyError(f"未知物品: {chain}/{tier}")

    def _add_item(self, chain: str, tier: int, cell: int | None = None) -> int | None:
        if cell is None:
            free = self.free_cells
            if not free:
                return None
            cell = free[0]
        item_def = self.item_definition(chain, tier)
        item = Item(
            uid=self._next_uid,
            chain=chain,
            tier=int(tier),
            name=item_def["name"],
            glyph=item_def["glyph"],
        )
        self._next_uid += 1
        self.board[cell] = item
        return cell

    def _draw_order(self) -> ActiveOrder:
        templates = self.config["orders"]
        template = self.rng.choice(templates)
        self._order_cursor += 1
        order = ActiveOrder(
            order_key=self._next_order_key,
            template_id=template["id"],
            title=template["title"],
            requirements=[dict(item) for item in template["requirements"]],
            reward=dict(template["reward"]),
        )
        self._next_order_key += 1
        return order

    def reset_daily_generators(self) -> None:
        self.generator_uses = {
            generator["id"]: int(generator["daily_uses"])
            for generator in self.config["generators"]
        }
        self._log("daily_reset", generators=dict(self.generator_uses))

    def add_daily_energy(self, amount: float | None = None) -> float:
        cap = float(self.config["economy"]["energy_cap"])
        amount = (
            float(self.config["economy"]["daily_energy_regen"])
            if amount is None
            else float(amount)
        )
        before = self.energy
        self.energy = min(cap, self.energy + amount)
        gained = self.energy - before
        self.stats["energy_gained"] += gained
        self._log("daily_energy", amount=round(gained, 2))
        return gained

    def generator(self, generator_id: str) -> dict[str, Any]:
        for generator in self.config["generators"]:
            if generator["id"] == generator_id:
                return generator
        raise KeyError(generator_id)

    def generate(self, generator_id: str) -> bool:
        generator = self.generator(generator_id)
        cost = float(generator["energy_cost"])
        if self.generator_uses.get(generator_id, 0) <= 0:
            self._log("generator_empty", generator=generator_id)
            return False
        if self.energy + 1e-9 < cost:
            self.stats["energy_blocked_attempts"] += 1
            self._log("energy_blocked", generator=generator_id, cost=cost)
            return False
        if not self.free_cells:
            self.stats["board_full_attempts"] += 1
            self._log("board_full", generator=generator_id)
            return False
        self.energy -= cost
        self.stats["energy_spent"] += cost
        self.generator_uses[generator_id] -= 1
        cell = self._add_item(generator["chain"], int(generator["tier"]))
        self.stats["generations"] += 1
        self._log(
            "generated",
            generator=generator_id,
            chain=generator["chain"],
            tier=int(generator["tier"]),
            cell=cell,
            energy_cost=cost,
        )
        return True

    def merge(self, first_cell: int, second_cell: int) -> bool:
        if first_cell == second_cell:
            return False
        first = self.board[first_cell] if 0 <= first_cell < self.capacity else None
        second = self.board[second_cell] if 0 <= second_cell < self.capacity else None
        if first is None or second is None:
            return False
        if first.chain != second.chain or first.tier != second.tier:
            return False
        max_tier = len(self.config["chains"][first.chain]["items"])
        if first.tier >= max_tier:
            return False
        self.board[first_cell] = None
        self.board[second_cell] = None
        result_cell = self._add_item(first.chain, first.tier + 1, cell=second_cell)
        self.stats["merges"] += 1
        self._log(
            "merged",
            chain=first.chain,
            from_tier=first.tier,
            to_tier=first.tier + 1,
            result_cell=result_cell,
        )
        return True

    def order_progress(self, order: ActiveOrder) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for requirement in order.requirements:
            available = sum(
                1
                for item in self.board
                if item
                and item.chain == requirement["chain"]
                and item.tier == int(requirement["tier"])
            )
            result.append(
                {
                    **requirement,
                    "available": available,
                    "ready": available >= int(requirement["count"]),
                }
            )
        return result

    def can_fulfill(self, order: ActiveOrder) -> bool:
        return all(progress["ready"] for progress in self.order_progress(order))

    def complete_order(self, order_index: int) -> bool:
        if not 0 <= order_index < len(self.active_orders):
            return False
        order = self.active_orders[order_index]
        if not self.can_fulfill(order):
            return False
        remaining = {
            (requirement["chain"], int(requirement["tier"])): int(requirement["count"])
            for requirement in order.requirements
        }
        for cell, item in enumerate(self.board):
            if item is None:
                continue
            key = (item.chain, item.tier)
            if remaining.get(key, 0) > 0:
                remaining[key] -= 1
                self.board[cell] = None
        coins = float(order.reward.get("coins", 0))
        stars = int(order.reward.get("stars", 0))
        self.coins += coins
        self.stars += stars
        self.stats["coins_earned"] += coins
        self.stats["stars_earned"] += stars
        self.stats["orders_completed"] += 1
        self._log(
            "order_completed",
            order_id=order.template_id,
            coins=coins,
            stars=stars,
        )
        self.active_orders[order_index] = self._draw_order()
        self.renovate_if_possible()
        return True

    def renovate_if_possible(self) -> bool:
        stage = self.next_renovation
        if stage is None:
            return False
        if self.stars < int(stage["stars_required"]):
            return False
        cost = float(stage["coins_required"])
        if self.coins + 1e-9 < cost:
            return False
        self.coins -= cost
        self.stats["coins_spent"] += cost
        self.stage_index += 1
        self.stats["stages_completed"] += 1
        self._log(
            "stage_completed",
            stage_id=stage["id"],
            stage_title=stage["title"],
            coins_spent=cost,
        )
        return True

    def buy_energy_with_gems(self) -> bool:
        cost = float(self.config["economy"]["gem_energy_cost"])
        amount = float(self.config["economy"]["gem_energy_amount"])
        if self.gems + 1e-9 < cost:
            return False
        cap = float(self.config["economy"]["energy_cap"])
        if self.energy >= cap:
            return False
        self.gems -= cost
        self.energy = min(cap, self.energy + amount)
        self.stats["energy_gained"] += amount
        self._log("gem_energy_exchange", gems_spent=cost, energy_added=amount)
        return True

    def find_pack(self, pack_id: str) -> dict[str, Any]:
        for pack in self.config["iap_packs"]:
            if pack["id"] == pack_id:
                return pack
        raise KeyError(pack_id)

    def can_purchase_pack(self, pack_id: str) -> bool:
        pack = self.find_pack(pack_id)
        if pack.get("one_time") and pack_id in self._purchased_one_time:
            return False
        return True

    def apply_purchase(self, pack_id: str) -> Purchase:
        pack = self.find_pack(pack_id)
        if not self.can_purchase_pack(pack_id):
            raise ValueError("该礼包不可重复购买")
        grants = {key: int(value) for key, value in pack["grants"].items()}
        self.gems += grants.get("gems", 0)
        self.energy += grants.get("energy", 0)
        self.coins += grants.get("coins", 0)
        self.stats["energy_gained"] += grants.get("energy", 0)
        self.stats["purchases"] += 1
        self.stats["iap_revenue_usd"] += float(pack["price_usd"])
        if pack.get("one_time"):
            self._purchased_one_time.add(pack_id)
        purchase = Purchase(
            pack_id=pack_id,
            name=pack["name"],
            price_usd=float(pack["price_usd"]),
            day=self.day,
            grants=grants,
        )
        self.purchases.append(purchase)
        self._log("iap_purchase", pack_id=pack_id, price_usd=float(pack["price_usd"]))
        self.renovate_if_possible()
        return purchase

    def record_offer(self, pack_id: str) -> None:
        self.stats["iap_offers"] += 1
        self._log("iap_offer", pack_id=pack_id)

    def summary(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "day": self.day,
            "energy": round(self.energy, 2),
            "coins": round(self.coins, 2),
            "gems": round(self.gems, 2),
            "stars": self.stars,
            "stage_index": self.stage_index,
            "board_items": self.item_count,
            **self.stats,
        }

    def board_rows(self) -> list[list[Item | None]]:
        return [
            self.board[row * self.cols : (row + 1) * self.cols]
            for row in range(self.rows)
        ]
