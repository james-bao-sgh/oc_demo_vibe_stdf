"""
Dash callbacks for STDF Analyzer.
Handles all user interaction and plot updates.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, State, callback, ctx, html, no_update, dcc
import yaml

from data_loader import parse_stdf, get_wafer_data, compute_cpk, _data_cache
import plots

logger = logging.getLogger(__name__)

CONFIG_PATH = "config.yaml"


def _load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def register_callbacks(app) -> None:
    config = _load_config()
    bin_colors = config.get("bin_colors", {})
    cpk_threshold = config.get("cpk_threshold", 1.33)

    @callback(
        Output("wafer-selector", "options"),
        Output("wafer-selector", "value"),
        Output("data-loaded-store", "data"),
        Output("load-status", "children"),
        Input("load-btn", "n_clicks"),
        State("file-path-input", "value"),
        prevent_initial_call=True,
    )
    def load_stdf_file(n_clicks, filepath):
        if not filepath:
            return no_update, no_update, no_update, "请输入文件路径"

        try:
            data = parse_stdf(filepath)
            _data_cache["current"] = data
            wafer_options = [{"label": w, "value": w} for w in data["wafers"]]
            first_wafer = data["current_wafer"] or (data["wafers"][0] if data["wafers"] else None)
            return (
                wafer_options,
                first_wafer,
                {"filepath": filepath, "loaded": True},
                f"加载成功: {Path(filepath).name} ({data['total_dies']} dies, {len(data['test_items'])} tests)"
            )
        except Exception as e:
            logger.exception("STDF load failed")
            return no_update, no_update, no_update, f"加载失败: {e}"

    @callback(
        Output("current-wafer-store", "data"),
        Output("selected-dies-store", "data"),
        Output("highlight-bin-store", "data"),
        Input("wafer-selector", "value"),
        prevent_initial_call=True,
    )
    def select_wafer(wafer_id):
        if not wafer_id or "current" not in _data_cache:
            return no_update, no_update, no_update
        return {"wafer_id": wafer_id}, [], None

    @callback(
        Output("test-item-selector", "options"),
        Output("test-item-selector", "value"),
        Input("wafer-selector", "value"),
        prevent_initial_call=True,
    )
    def update_test_items(wafer_id):
        if not wafer_id or "current" not in _data_cache:
            return [], None
        data = _data_cache["current"]
        wafer_data = get_wafer_data(data, wafer_id)
        items = wafer_data["test_items"]
        return [{"label": t, "value": t} for t in items], (items[0] if items else None)

    # ── Wafer map ──────────────────────────────────────────────
    @callback(
        Output("wafer-map", "figure"),
        Input("wafer-selector", "value"),
        Input("color-mode", "value"),
        Input("test-item-selector", "value"),
        Input("selected-dies-store", "data"),
        Input("highlight-bin-store", "data"),
        prevent_initial_call=True,
    )
    def update_wafer_map(wafer_id, color_mode, test_name,
                         selected_dies, highlight_bin):
        if not wafer_id or "current" not in _data_cache:
            return go.Figure()

        data = _data_cache["current"]
        wafer_data = get_wafer_data(data, wafer_id)

        return plots.create_wafer_map(
            die_df=wafer_data["die_info"],
            test_df=wafer_data["test_results"],
            color_mode=color_mode,
            test_name=test_name if color_mode == "test" else None,
            bin_colors=bin_colors,
            selected_dies=selected_dies or [],
            highlight_bin=highlight_bin,
        )

    # ── Scatter plot ───────────────────────────────────────────
    @callback(
        Output("scatter-plot", "figure"),
        Input("test-item-selector", "value"),
        Input("wafer-selector", "value"),
        Input("selected-dies-store", "data"),
        Input("scatter-mode", "value"),
        prevent_initial_call=True,
    )
    def update_scatter(test_name, wafer_id, selected_dies, scatter_mode):
        if not wafer_id or not test_name or "current" not in _data_cache:
            return go.Figure()

        data = _data_cache["current"]
        wafer_data = get_wafer_data(data, wafer_id)

        return plots.create_scatter_plot(
            die_df=wafer_data["die_info"],
            test_df=wafer_data["test_results"],
            test_name=test_name,
            selected_dies=selected_dies or None,
            x_axis="index",
            view_mode=scatter_mode or "normal",
        )

    # ── Pareto chart ───────────────────────────────────────────
    @callback(
        Output("pareto-chart", "figure"),
        Input("wafer-selector", "value"),
        Input("pareto-chart", "clickData"),
        prevent_initial_call=True,
    )
    def update_pareto(wafer_id, click_data):
        if not wafer_id or "current" not in _data_cache:
            return go.Figure()

        data = _data_cache["current"]
        wafer_data = get_wafer_data(data, wafer_id)

        selected_bin = None
        if click_data and "customdata" in click_data["points"][0]:
            selected_bin = int(click_data["points"][0]["customdata"])

        return plots.create_pareto_chart(
            die_df=wafer_data["die_info"],
            selected_bin=selected_bin,
        )

    # ── Die selection tracking ─────────────────────────────────
    @callback(
        Output("selected-dies-store", "data"),
        Output("highlight-bin-store", "data"),
        Input("wafer-map", "clickData"),
        Input("scatter-plot", "clickData"),
        Input("pareto-chart", "clickData"),
        State("wafer-selector", "value"),
        State("selected-dies-store", "data"),
        prevent_initial_call=True,
    )
    def track_selection(wafer_click, scatter_click, pareto_click,
                        wafer_id, current_selection):
        if not wafer_id or "current" not in _data_cache:
            return [], None

        triggered = ctx.triggered_id
        if triggered == "wafer-map" and wafer_click:
            pts = wafer_click["points"]
            if pts and "customdata" in pts[0]:
                cd = pts[0]["customdata"]
                die_idx = int(cd[0])
                hard_bin = int(cd[1]) if len(cd) > 1 else None
                return [die_idx], hard_bin

        elif triggered == "scatter-plot" and scatter_click:
            pts = scatter_click["points"]
            if pts and "customdata" in pts[0]:
                cd = pts[0]["customdata"]
                die_idx = int(cd[0]) if hasattr(cd, "__len__") else int(cd)
                data = _data_cache["current"]
                wafer_data = get_wafer_data(data, wafer_id)
                row = wafer_data["die_info"][
                    wafer_data["die_info"]["die_index"] == die_idx
                ]
                hb = int(row.iloc[0]["hard_bin"]) if not row.empty else None
                return [die_idx], hb

        elif triggered == "pareto-chart" and pareto_click:
            pts = pareto_click["points"]
            if pts and "customdata" in pts[0]:
                bin_val = int(pts[0]["customdata"])
                data = _data_cache["current"]
                wafer_data = get_wafer_data(data, wafer_id)
                bin_dies = wafer_data["die_info"][
                    wafer_data["die_info"]["hard_bin"] == bin_val
                ]["die_index"].tolist()
                return bin_dies, None

        return current_selection or [], no_update

    # ── Tracking panel: selected die info ──────────────────────
    @callback(
        Output("selected-die-info", "children"),
        Output("selected-die-table", "children"),
        Input("selected-dies-store", "data"),
        Input("wafer-selector", "value"),
        prevent_initial_call=True,
    )
    def update_tracking_panel(selected_dies, wafer_id):
        if not wafer_id or not selected_dies or "current" not in _data_cache:
            return "请点击芯片查看详情", ""

        data = _data_cache["current"]
        wafer_data = get_wafer_data(data, wafer_id)
        die_df = wafer_data["die_info"]
        test_df = wafer_data["test_results"]

        if len(selected_dies) == 1:
            die_idx = selected_dies[0]
            row = die_df[die_df["die_index"] == die_idx]
            if row.empty:
                return "芯片数据未找到", ""
            r = row.iloc[0]

            info = [
                f"芯片序号: {die_idx}",
                f"坐标: ({r['x_coord']:.1f}, {r['y_coord']:.1f})",
                f"硬 BIN: {int(r['hard_bin'])}",
                f"软 BIN: {int(r['soft_bin'])}",
                f"Site: {int(r['site'])}",
            ]

            die_tests = test_df[test_df["die_index"] == die_idx].copy()
            if die_tests.empty:
                table = html.Div("无测试数据")
            else:
                die_tests["Result"] = die_tests.apply(
                    lambda r: "PASS" if (
                        pd.isna(r["low_limit"]) or pd.isna(r["high_limit"]) or
                        r["low_limit"] <= r["result"] <= r["high_limit"]
                    ) else "FAIL", axis=1
                )
                rows = []
                for _, tr in die_tests.iterrows():
                    color = "red" if tr["Result"] == "FAIL" else "green"
                    rows.append(html.Tr([
                        html.Td(tr["test_name"]),
                        html.Td(f"{tr['result']:.4f}"),
                        html.Td(f"{tr['low_limit']:.4f}" if not pd.isna(tr["low_limit"]) else "-"),
                        html.Td(f"{tr['high_limit']:.4f}" if not pd.isna(tr["high_limit"]) else "-"),
                        html.Td(tr["Result"], style={"color": color, "fontWeight": "bold"}),
                    ]))

                table = html.Table(
                    [html.Thead(html.Tr([
                        html.Th("测试项"), html.Th("值"), html.Th("LSL"),
                        html.Th("USL"), html.Th("结果"),
                    ]))] + [html.Tbody(rows)],
                    style={"width": "100%", "fontSize": "12px", "borderCollapse": "collapse"},
                    className="table table-sm table-bordered",
                )

            return html.Div([html.P(line) for line in info]), table

        else:
            bin_counts = die_df[die_df["die_index"].isin(selected_dies)]["hard_bin"].value_counts()
            total = len(selected_dies)
            yield_in_selection = len(die_df[
                die_df["die_index"].isin(selected_dies) & (die_df["hard_bin"] == 1)
            ])

            info = [
                f"选中芯片数: {total}",
                f"良品数: {yield_in_selection}",
                f"良率: {yield_in_selection/total*100:.1f}%" if total > 0 else "良率: N/A",
            ]
            return html.Div([html.P(line) for line in info]), ""

    # ── Cpk update (暂时关闭) ─────────────────────────────────
    # @callback(
    #     Output("cpk-container", "children"),
    #     Input("wafer-selector", "value"),
    #     Input("color-mode", "value"),
    #     prevent_initial_call=True,
    # )
    # def update_cpk(wafer_id, _):
    #     ...

    # ── Export report ──────────────────────────────────────────
    @callback(
        Output("download-html", "data"),
        Output("download-pdf", "data"),
        Input("export-btn", "n_clicks"),
        State("wafer-selector", "value"),
        State("color-mode", "value"),
        State("test-item-selector", "value"),
        prevent_initial_call=True,
    )
    def export_report(n_clicks, wafer_id, color_mode, test_name):
        if not wafer_id or "current" not in _data_cache:
            return no_update, no_update

        data = _data_cache["current"]
        wafer_data = get_wafer_data(data, wafer_id)
        die_df = wafer_data["die_info"]
        test_df = wafer_data["test_results"]

        wf = plots.create_wafer_map(
            die_df=die_df, test_df=test_df,
            color_mode="bin", bin_colors=bin_colors,
        )
        pf = plots.create_pareto_chart(die_df=die_df)
        cpk_df = compute_cpk(test_df)
        cf = plots.create_cpk_cards(cpk_df, threshold=cpk_threshold)

        from report_generator import generate_report
        result = generate_report(
            die_df=die_df, test_df=test_df,
            wafer_id=wafer_id, cpk_df=cpk_df,
            wafer_map_fig=wf, pareto_fig=pf, cpk_fig=cf,
        )

        html_data = dcc.send_string(result.get("html", ""), f"report_{wafer_id}.html")
        pdf_b64 = result.get("pdf_b64", "")
        pdf_data = None
        if pdf_b64:
            import base64
            pdf_bytes = base64.b64decode(pdf_b64)
            pdf_data = dcc.send_bytes(pdf_bytes, f"report_{wafer_id}.pdf")

        return html_data, pdf_data
