from __future__ import annotations

import copy
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from engine.analytics import summarize_by_segment, summarize_cohort
from engine.loader import load_config
from engine.model import RestaurantGame
from engine.simulator import simulate_cohort


st.set_page_config(
    page_title="IAP 餐厅翻新 Merge-2",
    page_icon="🍽️",
    layout="wide",
)

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.6rem; padding-bottom: 2rem;}
    .hero {
        padding: 1.2rem 1.35rem;
        border-radius: 16px;
        background: linear-gradient(120deg, #f7ece7 0%, #f5f2df 52%, #eaf1df 100%);
        color: #332b27;
        margin-bottom: 1rem;
    }
    .hero h1 {font-size: 2rem; margin: 0 0 .35rem 0;}
    .hero p {margin: 0; color: #655b55;}
    .order-card {
        border: 1px solid #e2dcd7;
        border-radius: 14px;
        padding: 1rem;
        background: #fffdfb;
        min-height: 12rem;
    }
    .order-card h4 {margin: 0 0 .65rem 0;}
    .requirement-ready {color: #217a4a; font-weight: 600;}
    .requirement-waiting {color: #9a4c34;}
    </style>
    """,
    unsafe_allow_html=True,
)


def new_game(seed: int) -> RestaurantGame:
    config = load_config()
    return RestaurantGame(config, seed=seed)


config = load_config()

if "restaurant_game" not in st.session_state:
    st.session_state.restaurant_game = new_game(20261110)
if "merge_selected" not in st.session_state:
    st.session_state.merge_selected = None
if "restaurant_experiment" not in st.session_state:
    st.session_state.restaurant_experiment = None

game: RestaurantGame = st.session_state.restaurant_game

st.markdown(
    """
    <div class="hero">
      <h1>IAP 餐厅翻新 Merge-2｜数值与礼包经济</h1>
      <p>生成器消耗能量，二合升阶，订单产出金币与星星，装修推进剧情，礼包解决真实资源阻塞。</p>
    </div>
    """,
    unsafe_allow_html=True,
)

play_tab, store_tab, analysis_tab, design_tab = st.tabs(
    ["可玩原型", "IAP 商店", "合成队列分析", "设计说明"]
)

with play_tab:
    top_a, top_b, top_c, top_d = st.columns([1, 1, 1, 1])
    top_a.metric("能量", f"{game.energy:.0f}/{config['economy']['energy_cap']}")
    top_b.metric("金币", f"{game.coins:.0f}")
    top_c.metric("宝石", f"{game.gems:.0f}")
    top_d.metric("星星", game.stars)

    stage_col, action_col, new_col = st.columns([2.3, 1, 1])
    next_stage = game.next_renovation
    with stage_col:
        if next_stage:
            stage_col.write(
                f"**下一装修：{next_stage['title']}** · "
                f"需要 {next_stage['stars_required']} 星与 {next_stage['coins_required']} 金币"
            )
        else:
            stage_col.success("全部装修阶段已完成。")
    with action_col:
        if st.button("推进一天", use_container_width=True):
            game.day += 1
            game.add_daily_energy()
            game.reset_daily_generators()
            game.renovate_if_possible()
            st.rerun()
    with new_col:
        if st.button("新开经营档", use_container_width=True):
            st.session_state.restaurant_game = new_game(20261110 + game.day)
            st.session_state.merge_selected = None
            st.rerun()

    st.subheader("生成器")
    generator_cols = st.columns(len(config["generators"]))
    for column, generator in zip(generator_cols, config["generators"]):
        uses = game.generator_uses.get(generator["id"], 0)
        disabled = (
            uses <= 0
            or game.energy < float(generator["energy_cost"])
            or not game.free_cells
        )
        if column.button(
            f"{generator['name']}\n\n-{generator['energy_cost']} 能量 · 余 {uses}",
            key=f"gen-{generator['id']}-{game.day}-{uses}",
            use_container_width=True,
            disabled=disabled,
        ):
            game.generate(generator["id"])
            st.rerun()

    st.subheader("合并棋盘")
    st.caption(
        "点击两个同链同等级物品完成二合。物品会升一级并占用后一张牌的位置。"
    )
    selected = st.session_state.merge_selected
    for row_index in range(game.rows):
        columns = st.columns(game.cols)
        for col_index in range(game.cols):
            cell = row_index * game.cols + col_index
            item = game.board[cell]
            label = "·" if item is None else f"{item.glyph} T{item.tier}"
            is_selected = selected == cell
            if is_selected:
                label = f"✓ {label}"
            if columns[col_index].button(
                label,
                key=f"cell-{game.day}-{cell}-{None if item is None else item.uid}",
                use_container_width=True,
                disabled=item is None,
            ):
                if selected is None or selected == cell:
                    st.session_state.merge_selected = None if selected == cell else cell
                else:
                    first = game.board[selected]
                    if game.merge(selected, cell):
                        st.session_state.merge_selected = None
                    elif first is not None:
                        st.session_state.merge_selected = cell
                st.rerun()

    if selected is not None and game.board[selected] is not None:
        selected_item = game.board[selected]
        st.info(
            f"已选中：{selected_item.glyph} {selected_item.name} "
            f"（{config['chains'][selected_item.chain]['name']} T{selected_item.tier}）"
        )

    st.subheader("订单")
    order_cols = st.columns(len(game.active_orders))
    for index, (column, order) in enumerate(zip(order_cols, game.active_orders)):
        progress = game.order_progress(order)
        requirement_lines = []
        for requirement in progress:
            item_def = game.item_definition(requirement["chain"], requirement["tier"])
            css_class = "requirement-ready" if requirement["ready"] else "requirement-waiting"
            requirement_lines.append(
                f"<span class='{css_class}'>{item_def['glyph']} "
                f"{item_def['name']} {requirement['available']}/{requirement['count']}</span>"
            )
        column.markdown(
            "<div class='order-card'>"
            f"<h4>{order.title}</h4>"
            + "<br>".join(requirement_lines)
            + f"<p>奖励：{order.reward['coins']} 金币 · {order.reward['stars']} 星</p>"
            + "</div>",
            unsafe_allow_html=True,
        )
        if column.button(
            "交付订单",
            key=f"order-{order.order_key}",
            use_container_width=True,
            disabled=not game.can_fulfill(order),
        ):
            game.complete_order(index)
            st.rerun()

    data_a, data_b, data_c, data_d = st.columns(4)
    data_a.metric("完成订单", game.stats["orders_completed"])
    data_b.metric("合并次数", game.stats["merges"])
    data_c.metric("生成次数", game.stats["generations"])
    data_d.metric("装修阶段", game.stage_index)

    event_frame = pd.DataFrame(game.events)
    if not event_frame.empty:
        st.download_button(
            "下载经营事件日志",
            data=event_frame.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"restaurant_events_day{game.day}.csv",
            mime="text/csv",
        )

with store_tab:
    st.subheader("礼包目录")
    st.warning("这里是测算用模拟商店，不执行真实支付。")
    pack_cols = st.columns(2)
    for index, pack in enumerate(config["iap_packs"]):
        column = pack_cols[index % 2]
        grants = " · ".join(f"{key} +{value}" for key, value in pack["grants"].items())
        purchased_one_time = (
            pack.get("one_time") and pack["id"] in game._purchased_one_time
        )
        with column:
            st.markdown(f"### {pack['name']}")
            st.write(f"价格：${pack['price_usd']:.2f}")
            st.write(f"内容：{grants}")
            if st.button(
                "模拟购买",
                key=f"buy-{pack['id']}-{game.stats['purchases']}",
                use_container_width=True,
                disabled=bool(purchased_one_time),
            ):
                game.apply_purchase(pack["id"])
                st.rerun()

    st.subheader("宝石换能量")
    st.write(
        f"{config['economy']['gem_energy_cost']} 宝石换 "
        f"{config['economy']['gem_energy_amount']} 能量；能量达到上限时不可兑换。"
    )
    if st.button(
        "兑换能量",
        disabled=game.gems < config["economy"]["gem_energy_cost"]
        or game.energy >= config["economy"]["energy_cap"],
    ):
        game.buy_energy_with_gems()
        st.rerun()

with analysis_tab:
    st.subheader("14 天合成队列")
    st.write(
        "合成队列包含非付费、小额付费和中额付费三层。每次礼包提供都发生在能量不足、"
        "金币不足或棋盘阻塞之后，不把商店入口本身算作购买机会。"
    )
    sample_col, seed_col, run_col = st.columns([1, 1, 1])
    players = sample_col.number_input(
        "合成玩家数",
        min_value=100,
        max_value=3000,
        value=400,
        step=100,
    )
    cohort_seed = seed_col.number_input(
        "队列种子",
        min_value=1,
        max_value=99_999_999,
        value=20261110,
        step=1,
    )
    run_col.write("")
    run_col.write("")
    if run_col.button("运行合成队列", type="primary", use_container_width=True):
        with st.spinner("正在运行 14 天队列..."):
            standard_rows = simulate_cohort(
                config,
                players=int(players),
                seed=int(cohort_seed),
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
                players=int(players),
                seed=int(cohort_seed),
                scenario="低门槛开业包",
            )
            rows = standard_rows + starter_rows
            standard_summary = summarize_cohort(standard_rows)
            starter_summary = summarize_cohort(starter_rows)
            segment_rows = summarize_by_segment(standard_rows)
            st.session_state.restaurant_experiment = {
                "rows": rows,
                "comparison": pd.DataFrame(
                    [
                        {"scenario": "标准商店", **standard_summary},
                        {"scenario": "低门槛开业包", **starter_summary},
                    ]
                ),
                "segments": pd.DataFrame(segment_rows),
            }

    experiment = st.session_state.restaurant_experiment
    if experiment is None:
        st.info("点击“运行合成队列”生成本轮结果。")
    else:
        comparison = experiment["comparison"].copy()
        comparison_display = comparison[
            [
                "scenario",
                "payer_rate",
                "revenue_usd",
                "arppu_usd",
                "arpdau_usd",
                "avg_orders",
                "avg_stage_index",
                "avg_energy_block_days",
            ]
        ].copy()
        for column in ("payer_rate",):
            comparison_display[column] = comparison_display[column].map(
                lambda value: f"{float(value):.2%}"
            )
        for column in ("arppu_usd", "arpdau_usd", "avg_orders", "avg_stage_index", "avg_energy_block_days"):
            comparison_display[column] = comparison_display[column].map(
                lambda value: f"{float(value):.2f}"
            )
        comparison_display["revenue_usd"] = comparison_display["revenue_usd"].map(
            lambda value: f"${float(value):,.2f}"
        )
        st.dataframe(comparison_display, hide_index=True, use_container_width=True)

        segment_table = experiment["segments"].copy()
        segment_display = segment_table[
            [
                "segment_name",
                "players",
                "payer_rate",
                "avg_orders",
                "avg_stage_index",
                "avg_iap_offers",
                "avg_purchases",
                "revenue_usd",
            ]
        ].copy()
        segment_display["payer_rate"] = segment_display["payer_rate"].map(
            lambda value: f"{float(value):.2%}"
        )
        segment_display["revenue_usd"] = segment_display["revenue_usd"].map(
            lambda value: f"${float(value):,.2f}"
        )
        st.dataframe(segment_display, hide_index=True, use_container_width=True)

        figure = px.bar(
            comparison,
            x="scenario",
            y=["payer_rate", "avg_stage_index"],
            barmode="group",
            title="分层场景对比：付费率与第 14 日平均阶段（量纲不同，仅并列观察）",
        )
        st.plotly_chart(figure, use_container_width=True)

        downloads_a, downloads_b = st.columns(2)
        downloads_a.download_button(
            "下载场景汇总 CSV",
            data=comparison.to_csv(index=False).encode("utf-8-sig"),
            file_name="restaurant_scenario_summary.csv",
            mime="text/csv",
            use_container_width=True,
        )
        downloads_b.download_button(
            "下载玩家明细 CSV",
            data=pd.DataFrame(experiment["rows"]).to_csv(index=False).encode("utf-8-sig"),
            file_name="restaurant_player_runs.csv",
            mime="text/csv",
            use_container_width=True,
        )

with design_tab:
    st.subheader("核心循环")
    st.write(
        "生成器消耗能量 → 两个同链同级物品二合升阶 → 订单消费高阶物品 → "
        "订单产出金币与星星 → 金币和累计星星推进装修 → 能量阻塞时出现 IAP。"
    )
    st.subheader("IAP 设计原则")
    st.write("1. 礼包只解决已经出现的资源阻塞，不把纯商店曝光当作付费机会。")
    st.write("2. 礼包同时包含即时资源与可延期资源，避免一次购买完全跳过经营循环。")
    st.write("3. 非付费玩家仍可通过每日能量完成订单和装修，只是推进速度较慢。")
    st.subheader("分析指标")
    st.write(
        "付费率、ARPPU、ARPDAU、订单完成、二合次数、装修阶段、能量阻塞日、"
        "棋盘阻塞日、礼包提供、购买次数和分层收入。"
    )
    with st.expander("当前模型配置"):
        st.json(
            {
                "board": config["board"],
                "economy": config["economy"],
                "simulation": config["simulation"],
                "player_segments": config["player_segments"],
                "packs": config["iap_packs"],
                "renovations": config["renovations"],
            }
        )
