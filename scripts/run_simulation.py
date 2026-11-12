from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from engine.analytics import write_csv, write_json, summarize_by_segment, summarize_cohort
from engine.loader import load_config
from engine.simulator import simulate_cohort


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--players", type=int, default=1200)
    parser.add_argument("--seed", type=int, default=20261110)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_DIR / "outputs")
    args = parser.parse_args()

    config = load_config()
    standard_rows = simulate_cohort(
        config,
        players=args.players,
        seed=args.seed,
        scenario="标准商店",
    )
    starter_config = copy.deepcopy(config)
    starter = next(
        pack for pack in starter_config["iap_packs"] if pack["id"] == "starter_pack"
    )
    starter["price_usd"] = 1.99
    starter["grants"] = {"gems": 250, "energy": 150, "coins": 500}
    starter_rows = simulate_cohort(
        starter_config,
        players=args.players,
        seed=args.seed,
        scenario="低门槛开业包",
    )
    rows = standard_rows + starter_rows
    summary = summarize_cohort(standard_rows)
    starter_summary = summarize_cohort(starter_rows)
    segment_summary = summarize_by_segment(standard_rows)

    output_dir = args.output_dir
    write_csv(output_dir / "player_runs.csv", rows)
    write_csv(output_dir / "segment_summary.csv", segment_summary)
    write_json(output_dir / "cohort_summary.json", summary)
    write_json(
        output_dir / "scenario_summary.json",
        {
            "标准商店": summary,
            "低门槛开业包": starter_summary,
        },
    )
    write_csv(
        output_dir / "scenario_summary.csv",
        [
            {"scenario": "标准商店", **summary},
            {"scenario": "低门槛开业包", **starter_summary},
        ],
    )
    write_json(
        output_dir / "run_metadata.json",
        {
            "players": args.players,
            "seed": args.seed,
            "days": config["simulation"]["days"],
            "reference_note": config["meta"]["reference_note"],
        },
    )

    report = [
        "# IAP 餐厅翻新 Merge-2 合成队列报告",
        "",
        "优先级：U1",
        "",
        "本报告基于机器人行为、假设分层和假设礼包，不代表真实市场数据或收入预测。",
        "",
        "## 队列结果",
        "",
        f"- 样本玩家：{summary['players']:,}",
        f"- 合成付费率：{summary['payer_rate']:.2%}",
        f"- 合成 ARPPU：${summary['arppu_usd']:.2f}",
        f"- 合成 ARPDAU：${summary['arpdau_usd']:.3f}",
        f"- 人均完成订单：{summary['avg_orders']:.1f}",
        f"- 活跃日人均订单：{summary['avg_orders'] / max(1.0, summary['avg_active_days']):.2f}",
        f"- 人均二合次数：{summary['avg_merges']:.1f}",
        f"- 人均第 14 日装修阶段：{summary['avg_stage_index']:.2f}",
        f"- 至少完成 3 个装修阶段的比例：{summary['stage_3_rate']:.1%}",
        f"- 标准商店收入：${summary['revenue_usd']:,.2f}",
        f"- 低门槛开业包收入：${starter_summary['revenue_usd']:,.2f}",
        f"- 低门槛开业包付费率：{starter_summary['payer_rate']:.2%}；"
        f"ARPPU ${starter_summary['arppu_usd']:.2f}",
        "",
        "## 分层结果",
        "",
        "| 分层 | 样本 | 付费率 | 人均订单 | 人均购买 | 人均收入 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in segment_summary:
        report.append(
            f"| {row['segment_name']} | {row['players']} | {row['payer_rate']:.2%} | "
            f"{row['avg_orders']:.1f} | {row['avg_purchases']:.2f} | "
            f"${row['revenue_usd'] / row['players']:.2f} |"
        )
    report.extend(
        [
            "",
            "## 分析结论",
            "",
            f"- 合成结果中平均每名玩家在 14 天出现 "
            f"{summary['avg_energy_block_days']:.2f} 个能量受阻日，"
            f"{summary['avg_board_block_days']:.2f} 个棋盘受阻日。",
            f"- 标准开业包为 ${2.99:.2f}，低门槛情景为 ${1.99:.2f}。"
            f"两种情景付费率分别为 {summary['payer_rate']:.2%} 与 "
            f"{starter_summary['payer_rate']:.2%}；收入分别为 "
            f"${summary['revenue_usd']:,.2f} 与 ${starter_summary['revenue_usd']:,.2f}。"
            "当前合成结果应先用于检查价格与触发假设，不直接推导价格弹性。",
            "- 能量礼包和开业包只在真实阻塞后提供，避免把商店入口本身当成转化漏斗。",
            "- 订单同时产金币和星星；装修消耗金币并检查累计星星，防止只靠单一软货币推进。",
            "- 该模型用于说明 IAP 礼包结构、合成队列和指标联动的设计方法，不用于预测市场基准。",
            "",
        ]
    )
    (output_dir / "COHORT_REPORT.md").write_text("\n".join(report), encoding="utf-8")
    print(json.dumps({"players": len(rows), "monthly_revenue_synthetic": summary["revenue_usd"]}))
    print(f"outputs: {output_dir}")


if __name__ == "__main__":
    main()
