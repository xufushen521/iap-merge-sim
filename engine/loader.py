from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_DIR / "config.json"


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    with config_path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    validate_config(config)
    return config


def validate_config(config: dict[str, Any]) -> None:
    required = {
        "meta",
        "board",
        "economy",
        "generation",
        "chains",
        "generators",
        "starting_items",
        "orders",
        "renovations",
        "iap_packs",
        "player_segments",
        "simulation",
    }
    missing = required.difference(config)
    if missing:
        raise ValueError(f"配置缺少字段: {sorted(missing)}")

    capacity = int(config["board"]["rows"]) * int(config["board"]["cols"])
    if capacity < len(config["starting_items"]):
        raise ValueError("初始物品数量超过棋盘容量")

    chains = config["chains"]
    item_keys: set[tuple[str, int]] = set()
    for chain_id, chain in chains.items():
        tiers = [int(item["tier"]) for item in chain["items"]]
        if tiers != list(range(1, len(tiers) + 1)):
            raise ValueError(f"链 {chain_id} 的等级必须从 1 连续递增")
        item_keys.update((chain_id, tier) for tier in tiers)

    for generator in config["generators"]:
        key = (generator["chain"], int(generator["tier"]))
        if key not in item_keys:
            raise ValueError(f"生成器 {generator['id']} 指向不存在的物品")
        if int(generator["energy_cost"]) < 0 or int(generator["daily_uses"]) < 0:
            raise ValueError(f"生成器 {generator['id']} 的成本或次数不能为负数")

    for order in config["orders"]:
        for requirement in order["requirements"]:
            key = (requirement["chain"], int(requirement["tier"]))
            if key not in item_keys:
                raise ValueError(f"订单 {order['id']} 需要不存在的物品 {key}")
            if int(requirement["count"]) <= 0:
                raise ValueError(f"订单 {order['id']} 的需求数量必须为正数")

    stage_requirements = [
        (int(stage["stars_required"]), int(stage["coins_required"]))
        for stage in config["renovations"]
    ]
    if stage_requirements != sorted(stage_requirements):
        raise ValueError("装修阶段的星星和金币要求必须单调递增")

    pack_ids: set[str] = set()
    for pack in config["iap_packs"]:
        if pack["id"] in pack_ids:
            raise ValueError(f"IAP 礼包 ID 重复: {pack['id']}")
        pack_ids.add(pack["id"])
        if float(pack["price_usd"]) <= 0:
            raise ValueError(f"礼包 {pack['id']} 的价格必须为正数")
        if not set(pack["grants"]).issubset({"gems", "energy", "coins"}):
            raise ValueError(f"礼包 {pack['id']} 包含未知资源")

    shares = sum(float(segment["share"]) for segment in config["player_segments"])
    if abs(shares - 1.0) > 1e-6:
        raise ValueError("玩家分层 share 之和必须为 1")
    for segment in config["player_segments"]:
        for key in ("daily_visit_probability", "offer_buy_probability"):
            value = float(segment[key])
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"玩家分层 {segment['id']} 的 {key} 必须在 0–1")
