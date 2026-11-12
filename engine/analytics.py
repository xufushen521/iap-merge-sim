from __future__ import annotations

import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


def summarize_cohort(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    payers = [row for row in rows if row["is_payer"]]
    revenue = sum(float(row["iap_revenue_usd"]) for row in rows)
    player_days = sum(int(row["active_days"]) for row in rows)
    summary = {
        "players": len(rows),
        "avg_active_days": statistics.fmean(float(row["active_days"]) for row in rows),
        "payer_rate": len(payers) / len(rows),
        "revenue_usd": revenue,
        "arppu_usd": revenue / max(1, len(payers)),
        "arpdau_usd": revenue / max(1, player_days),
        "avg_orders": statistics.fmean(float(row["orders_completed"]) for row in rows),
        "avg_merges": statistics.fmean(float(row["merges"]) for row in rows),
        "avg_generations": statistics.fmean(float(row["generations"]) for row in rows),
        "avg_energy_spent": statistics.fmean(float(row["energy_spent"]) for row in rows),
        "avg_energy_gained": statistics.fmean(float(row["energy_gained"]) for row in rows),
        "avg_coins_earned": statistics.fmean(float(row["coins_earned"]) for row in rows),
        "avg_coins_spent": statistics.fmean(float(row["coins_spent"]) for row in rows),
        "avg_stage_index": statistics.fmean(float(row["stage_index"]) for row in rows),
        "stage_3_rate": sum(1 for row in rows if int(row["stage_index"]) >= 3) / len(rows),
        "avg_energy_block_days": statistics.fmean(
            float(row["energy_block_days"]) for row in rows
        ),
        "avg_board_block_days": statistics.fmean(
            float(row["board_block_days"]) for row in rows
        ),
        "avg_iap_offers": statistics.fmean(float(row["iap_offers"]) for row in rows),
        "avg_purchases": statistics.fmean(float(row["purchases"]) for row in rows),
    }
    return summary


def summarize_by_segment(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["segment_id"]].append(row)
    output = []
    for segment_id, segment_rows in sorted(groups.items()):
        summary = summarize_cohort(segment_rows)
        summary["segment_id"] = segment_id
        summary["segment_name"] = segment_rows[0]["segment_name"]
        output.append(summary)
    return output


def summarize_by_simulation_day(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    day_rows: list[dict[str, Any]] = []
    for day in range(1, max(int(row["active_days"]) for row in rows) + 1):
        denominator = len(rows)
        day_rows.append(
            {
                "day": day,
                "cumulative_payer_rate": sum(
                    1
                    for row in rows
                    if int(row["purchases"]) > 0
                )
                / denominator,
                "avg_cumulative_orders_proxy": statistics.fmean(
                    float(row["orders_completed"]) / max(1, int(row["active_days"])) * day
                    for row in rows
                ),
                "avg_stage_proxy": statistics.fmean(
                    float(row["stage_index"]) for row in rows
                ),
            }
        )
    return day_rows


def write_csv(path: str | Path, rows: list[dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0])
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: str | Path, payload: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
