from __future__ import annotations

import random
from typing import Any

from .model import RestaurantGame


def _pick_segment(config: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    value = rng.random()
    cumulative = 0.0
    for segment in config["player_segments"]:
        cumulative += float(segment["share"])
        if value <= cumulative:
            return segment
    return config["player_segments"][-1]


def _best_order(game: RestaurantGame) -> int | None:
    ready = [
        (index, order)
        for index, order in enumerate(game.active_orders)
        if game.can_fulfill(order)
    ]
    if not ready:
        return None
    index, _ = max(
        ready,
        key=lambda pair: (
            pair[1].reward.get("stars", 0) * 100 + pair[1].reward.get("coins", 0),
            -pair[0],
        ),
    )
    return index


def _best_merge(game: RestaurantGame) -> tuple[int, int] | None:
    by_key: dict[tuple[str, int], list[int]] = {}
    for cell, item in enumerate(game.board):
        if item is None:
            continue
        by_key.setdefault((item.chain, item.tier), []).append(cell)
    candidates = [
        (cells[0], cells[1], tier)
        for (_, tier), cells in by_key.items()
        if len(cells) >= 2
    ]
    if not candidates:
        return None
    first, second, _ = min(candidates, key=lambda item: (item[2], item[0], item[1]))
    return first, second


def _best_generator(game: RestaurantGame) -> str | None:
    available = [
        generator
        for generator in game.config["generators"]
        if game.generator_uses.get(generator["id"], 0) > 0
        and game.energy + 1e-9 >= float(generator["energy_cost"])
    ]
    if not available:
        return None
    generator = max(
        available,
        key=lambda item: (
            game.generator_uses.get(item["id"], 0),
            -float(item["energy_cost"]),
        ),
    )
    return generator["id"]


def _candidate_pack(game: RestaurantGame, segment: dict[str, Any], day: int) -> str | None:
    packs = {pack["id"]: pack for pack in game.config["iap_packs"]}
    budget = float(segment["daily_budget"])
    if budget <= 0:
        return None
    if (
        "starter_pack" in packs
        and game.can_purchase_pack("starter_pack")
        and day <= 2
        and float(packs["starter_pack"]["price_usd"]) <= budget
    ):
        return "starter_pack"
    if game.energy < float(game.config["generation"]["energy_cost"]):
        for pack_id in ("energy_pack", "starter_pack", "value_pack"):
            if pack_id in packs and float(packs[pack_id]["price_usd"]) <= budget:
                return pack_id
    next_stage = game.next_renovation
    if (
        next_stage is not None
        and game.stars >= int(next_stage["stars_required"])
        and game.coins < float(next_stage["coins_required"])
    ):
        for pack_id in ("value_pack", "starter_pack"):
            if pack_id in packs and float(packs[pack_id]["price_usd"]) <= budget:
                return pack_id
    return None


def _maybe_purchase(
    game: RestaurantGame,
    segment: dict[str, Any],
    day: int,
    rng: random.Random,
) -> bool:
    pack_id = _candidate_pack(game, segment, day)
    if pack_id is None:
        return False
    game.record_offer(pack_id)
    if rng.random() >= float(segment["offer_buy_probability"]):
        game._log("iap_declined", pack_id=pack_id)
        return False
    game.apply_purchase(pack_id)
    return True


def simulate_player(
    config: dict[str, Any],
    player_index: int,
    seed: int | None = None,
    record_events: bool = False,
    scenario: str = "标准商店",
) -> dict[str, Any]:
    actual_seed = int(seed if seed is not None else config["simulation"]["default_seed"]) + player_index
    rng = random.Random(actual_seed ^ 0xA5A5A5A5)
    segment = _pick_segment(config, rng)
    game = RestaurantGame(config, actual_seed, record_events=record_events)
    days = int(config["simulation"]["days"])
    action_limit = int(config["simulation"]["session_action_limit"])
    target_orders = int(config["simulation"]["daily_target_orders"])
    energy_block_days = 0
    board_block_days = 0
    declined_offers = 0
    active_days = 0

    for day in range(1, days + 1):
        game.day = day
        if rng.random() > float(segment.get("daily_visit_probability", 1.0)):
            game._log("day_skipped")
            continue
        active_days += 1
        if day > 1:
            game.add_daily_energy()
        game.reset_daily_generators()
        daily_orders = 0
        daily_purchase_attempted = False
        actions = 0
        while actions < action_limit and daily_orders < target_orders:
            actions += 1
            game.renovate_if_possible()
            order_index = _best_order(game)
            if order_index is not None:
                game.complete_order(order_index)
                daily_orders += 1
                continue
            merge_cells = _best_merge(game)
            if merge_cells is not None:
                game.merge(*merge_cells)
                continue
            generator_id = _best_generator(game)
            if generator_id is not None and game.free_cells:
                game.generate(generator_id)
                continue

            if game.energy < float(game.config["generation"]["energy_cost"]):
                energy_block_days += 1
                game._log("session_blocked_energy")
            elif not game.free_cells:
                board_block_days += 1
                game._log("session_blocked_board")

            if daily_purchase_attempted:
                break
            daily_purchase_attempted = True
            offers_before = game.stats["iap_offers"]
            if not _maybe_purchase(game, segment, day, rng):
                if game.stats["iap_offers"] > offers_before:
                    declined_offers += 1
                break

    summary = game.summary()
    summary.update(
        {
            "player_id": f"P{player_index + 1:05d}",
            "segment_id": segment["id"],
            "segment_name": segment["name"],
            "scenario": scenario,
            "energy_block_days": min(energy_block_days, days),
            "board_block_days": min(board_block_days, days),
            "declined_offers": declined_offers,
            "is_payer": game.stats["purchases"] > 0,
            "active_days": max(1, active_days),
            "simulated_days": days,
            "events": game.events,
        }
    )
    if not record_events:
        summary.pop("events", None)
    return summary


def simulate_cohort(
    config: dict[str, Any],
    players: int | None = None,
    seed: int | None = None,
    scenario: str = "标准商店",
    record_events: bool = False,
) -> list[dict[str, Any]]:
    players = players or int(config["simulation"]["default_players"])
    seed = seed or int(config["simulation"]["default_seed"])
    return [
        simulate_player(
            config,
            player_index,
            seed=seed,
            record_events=record_events,
            scenario=scenario,
        )
        for player_index in range(players)
    ]
