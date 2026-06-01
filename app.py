"""
STDF Wafer Data Analyzer — Plotly Dash Web Application.

Usage:
    python app.py
"""

import logging
import os
import sys
from pathlib import Path

import dash_bootstrap_components as dbc
from dash import Dash, html, dcc

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    suppress_callback_exceptions=True,
    title="STDF Wafer Analyzer",
)

app.layout = dbc.Container([
    dcc.Store(id="data-loaded-store", data={"loaded": False}),
    dcc.Store(id="current-wafer-store", data={}),
    dcc.Store(id="selected-dies-store", data=[]),
    dcc.Store(id="highlight-bin-store", data=None),

    # ── Title ──
    dbc.Row([
        dbc.Col(html.H2("STDF 晶圆数据分析工具", className="text-center mt-3 mb-2"), width=12),
    ]),

    dcc.Loading(
        id="loading-main",
        type="circle",
        color="#119DFF",
        parent_style=dict(position="relative", minHeight="300px"),
        children=html.Div([
            # ── Top bar: file input + controls ──
            dbc.Row([
                dbc.Col([
                    dbc.InputGroup([
                        dbc.Input(
                            id="file-path-input",
                            placeholder=r"输入 STDF 文件完整路径，如 D:\data\wafer.stdf",
                            type="text",
                        ),
                        dbc.Button("加载", id="load-btn", color="primary", n_clicks=0),
                        dbc.Button("导出报告", id="export-btn", color="secondary", n_clicks=0,
                                   className="ms-2"),
                    ]),
                    html.Div(id="load-status", className="mt-1 text-muted", style={"fontSize": "13px"}),
                ], width=9),
                dbc.Col([
                    dcc.Dropdown(id="wafer-selector", placeholder="选择晶圆"),
                ], width=3),
            ], className="mb-2"),

            # ── Main content: left charts + right panel ──
            dbc.Row([
                # ===== Left column: charts =====
                dbc.Col([
                    dbc.Card([
                        dbc.Tabs([
                            dbc.Tab(dcc.Graph(id="wafer-map", config={"displayModeBar": False}),
                                    label="晶圆图", tab_id="tab-wafer"),
                            dbc.Tab(dcc.Graph(id="scatter-plot", config={"displayModeBar": False}),
                                    label="散点图", tab_id="tab-scatter"),
                            dbc.Tab(dcc.Graph(id="pareto-chart", config={"displayModeBar": False}),
                                    label="BIN Pareto", tab_id="tab-pareto"),
                        ], id="chart-tabs", active_tab="tab-wafer"),
                    ], body=True, className="mb-2"),
                ], width=8, lg=8),

                # ===== Right column: config + tracking =====
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("配置面板"),
                        dbc.CardBody([
                            html.Label("着色模式", className="fw-bold"),
                            dcc.RadioItems(
                                id="color-mode",
                                options=[
                                    {"label": "按 BIN 着色", "value": "bin"},
                                    {"label": "按测试值着色", "value": "test"},
                                ],
                                value="bin",
                                labelStyle=dict(display="block"),
                            ),
                            html.Hr(),
                            html.Label("测试项", className="fw-bold"),
                            dcc.Dropdown(id="test-item-selector", placeholder="选择测试项"),
                            html.Hr(),
                            html.Label("散点图模式", className="fw-bold"),
                            dcc.RadioItems(
                                id="scatter-mode",
                                options=[
                                    {"label": "默认显示", "value": "normal"},
                                    {"label": "显示 Min/Max", "value": "minmax"},
                                    {"label": "仅 BIN1", "value": "bin1"},
                                ],
                                value="normal",
                                labelStyle=dict(display="block", fontSize="13px"),
                            ),
                        ]),
                    ], className="mb-2"),

                    dbc.Card([
                        dbc.CardHeader("追踪面板"),
                        dbc.CardBody([
                            html.Div(id="selected-die-info", children="请点击芯片查看详情",
                                     style={"marginBottom": "10px", "fontSize": "13px"}),
                            html.Div(id="selected-die-table", children=""),
                        ]),
                    ], className="mb-2"),
                ], width=4, lg=4),
            ]),
        ]),
    ),

    # ── Download stores ──
    dcc.Download(id="download-html"),
    dcc.Download(id="download-pdf"),

    # ── Footer ──
    html.Hr(),
    html.P("STDF Wafer Analyzer v1.0 | 基于 Plotly Dash 构建",
           className="text-center text-muted", style={"fontSize": "12px"}),
], fluid=True)


def main():
    from callbacks import register_callbacks
    register_callbacks(app)

    port = int(os.environ.get("PORT", 8050))
    debug = os.environ.get("DEBUG", "").lower() in ("1", "true", "yes")

    logger.info(f"Starting STDF Analyzer on http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=debug)


if __name__ == "__main__":
    main()
