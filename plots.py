"""
Plotly chart construction for STDF wafer analysis.
"""

from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def create_wafer_map(
    die_df: pd.DataFrame,
    test_df: pd.DataFrame,
    color_mode: str = "bin",
    test_name: Optional[str] = None,
    bin_colors: Optional[Dict[int, str]] = None,
    selected_dies: Optional[List[int]] = None,
    highlight_bin: Optional[int] = None,
) -> go.Figure:
    if die_df.empty:
        return go.Figure()

    if bin_colors is None:
        bin_colors = {}
    other_color = bin_colors.pop("other", "#7F7F7F")

    fig = go.Figure()

    x = die_df["x_coord"].values
    y = die_df["y_coord"].values
    die_indices = die_df["die_index"].values
    hard_bins = die_df["hard_bin"].values

    is_selected = np.zeros(len(die_df), dtype=bool)
    if selected_dies:
        is_selected = np.isin(die_indices, selected_dies)

    if color_mode == "bin":
        unique_bins = sorted(set(hard_bins))
        for b in unique_bins:
            mask = (hard_bins == b) & (~is_selected)
            if mask.any():
                if int(b) == 1:
                    color = bin_colors.get(int(b), other_color)
                elif int(b) == 65535:
                    color = "#7F7F7F"
                else:
                    color = "#EF553B"
                fig.add_trace(go.Scattergl(
                    x=x[mask], y=y[mask],
                    mode="markers",
                    marker=dict(size=12, symbol="square", color=color, line=dict(width=0.5, color="white")),
                    name=f"BIN {int(b)}",
                    customdata=np.stack([
                        die_indices[mask],
                        np.full(mask.sum(), int(b)),
                    ], axis=1),
                    hovertemplate=(
                        "Die %{customdata[0]}<br>BIN %{customdata[1]}<br>"
                        "X: %{x:.1f}<br>Y: %{y:.1f}<extra></extra>"
                    ),
                ))

        if is_selected.any():
            sel_mask = is_selected
            if highlight_bin is not None:
                same_bin_mask = (hard_bins == highlight_bin) & (~is_selected)
                if same_bin_mask.any():
                    fig.add_trace(go.Scattergl(
                        x=x[same_bin_mask], y=y[same_bin_mask],
                        mode="markers",
                        marker=dict(
                            size=12, symbol="square",
                            color=bin_colors.get(int(highlight_bin), other_color) if int(highlight_bin) == 1 else ("#7F7F7F" if int(highlight_bin) == 65535 else "#EF553B"),
                            opacity=0.35, line=dict(width=0.5, color="white"),
                        ),
                        name=f"同 BIN {int(highlight_bin)}",
                        hoverinfo="skip",
                    ))

            sel_bin = int(hard_bins[sel_mask][0])
            sel_color = bin_colors.get(sel_bin, other_color) if sel_bin == 1 else ("#7F7F7F" if sel_bin == 65535 else "#EF553B")
            fig.add_trace(go.Scattergl(
                x=x[sel_mask], y=y[sel_mask],
                mode="markers",
                marker=dict(
                    size=12, symbol="square",
                    color=sel_color,
                    line=dict(width=2, color="black"),
                ),
                name="选中芯片",
                customdata=np.stack([
                    die_indices[sel_mask],
                    hard_bins[sel_mask],
                ], axis=1),
                hovertemplate=(
                    "Die %{customdata[0]}<br>BIN %{customdata[1]}<br>"
                    "X: %{x:.1f}<br>Y: %{y:.1f}<extra></extra>"
                ),
            ))
    else:
        if test_name is None or test_name not in test_df["test_name"].values:
            fig.update_layout(title="请选择测试项")
            return fig

        test_vals_map = dict(
            zip(test_df[test_df["test_name"] == test_name]["die_index"],
                test_df[test_df["test_name"] == test_name]["result"])
        )
        test_vals = np.array([test_vals_map.get(di, np.nan) for di in die_indices])

        base_mask = ~np.isnan(test_vals) & (~is_selected)
        fig.add_trace(go.Scattergl(
            x=x[base_mask], y=y[base_mask],
            mode="markers",
            marker=dict(
                size=12, symbol="square",
                color=test_vals[base_mask],
                colorscale="Viridis",
                showscale=True,
                colorbar=dict(title=test_name, thickness=15),
                line=dict(width=0.5, color="white"),
            ),
            name=test_name,
            customdata=np.stack([
                die_indices[base_mask],
                test_vals[base_mask],
            ], axis=1),
            hovertemplate=(
                "Die %{customdata[0]}<br>%{customdata[1]:.3f}<br>"
                "X: %{x:.1f}<br>Y: %{y:.1f}<extra></extra>"
            ),
        ))

        if is_selected.any():
            fig.add_trace(go.Scattergl(
                x=x[is_selected], y=y[is_selected],
                mode="markers",
                marker=dict(
                    size=12, symbol="square",
                    color=test_vals[is_selected],
                    colorscale="Viridis",
                    line=dict(width=2, color="black"),
                    showscale=False,
                ),
                name="选中芯片",
                customdata=np.stack([
                    die_indices[is_selected],
                    test_vals[is_selected],
                ], axis=1),
                hovertemplate=(
                    "Die %{customdata[0]}<br>%{customdata[1]:.3f}<br>"
                    "X: %{x:.1f}<br>Y: %{y:.1f}<extra></extra>"
                ),
            ))

        nan_mask = np.isnan(test_vals) & (~is_selected)
        if nan_mask.any():
            fig.add_trace(go.Scattergl(
                x=x[nan_mask], y=y[nan_mask],
                mode="markers",
                marker=dict(size=12, color="lightgray", symbol="square"),
                name="无数据",
                hoverinfo="skip",
            ))

    fig.update_layout(
        xaxis=dict(scaleanchor="y", constrain="domain", title="X (mm)"),
        yaxis=dict(title="Y (mm)"),
        height=1080,
        margin=dict(l=20, r=20, t=30, b=20),
        hovermode="closest",
        clickmode="event+select",
        legend=dict(font=dict(size=9), yanchor="top", y=0.99, xanchor="right", x=0.99),
    )
    fig.update_xaxes(showgrid=False, zeroline=False)
    fig.update_yaxes(showgrid=False, zeroline=False)
    return fig


def create_scatter_plot(
    die_df: pd.DataFrame,
    test_df: pd.DataFrame,
    test_name: str,
    selected_dies: Optional[List[int]] = None,
    x_axis: str = "index",
    y_axis: Optional[str] = None,
    view_mode: str = "normal",
) -> go.Figure:
    if die_df.empty or test_df.empty or not test_name:
        return go.Figure()

    if test_name not in test_df["test_name"].values:
        return go.Figure()

    die = die_df.reset_index(drop=True)
    die["_device_id"] = range(len(die))

    merge_keys = ["die_index", "head", "site"]
    on_cols = [c for c in merge_keys if c in die.columns and c in test_df.columns]
    if not on_cols:
        on_cols = ["die_index"]

    left = die[on_cols + ["_device_id", "hard_bin"]]
    right = test_df[test_df["test_name"] == test_name][on_cols + ["result", "low_limit", "high_limit"]]

    merged = left.merge(right, on=on_cols, how="left")

    if merged.empty:
        return go.Figure()

    fig = go.Figure()

    x_vals = merged["_device_id"].values
    x_label = "Device Index"

    y_vals = merged["result"].values
    lsl = merged["low_limit"].values if "low_limit" in merged.columns else None
    usl = merged["high_limit"].values if "high_limit" in merged.columns else None
    hb = merged["hard_bin"].values if "hard_bin" in merged.columns else None

    # Filter by view mode
    has_data = ~np.isnan(y_vals)
    if view_mode == "bin1" and hb is not None:
        has_data = has_data & (hb == 1)

    is_selected = np.zeros(len(merged), dtype=bool)
    if selected_dies:
        is_selected = np.isin(merged["die_index"].values, selected_dies)

    base_mask = has_data & ~is_selected
    if base_mask.any():
        fig.add_trace(go.Scattergl(
            x=x_vals[base_mask], y=y_vals[base_mask],
            mode="markers",
            marker=dict(size=5, color="#636EFA", line=dict(width=0.5, color="white")),
            name=test_name,
            customdata=merged.loc[base_mask, ["die_index", "head", "site"]].values,
            hovertemplate=(
                "Die %{customdata[0]} | H%{customdata[1]} S%{customdata[2]}<br>"
                f"{test_name}: %{{y:.3f}}<extra></extra>"
            ),
        ))

    sel_mask = has_data & is_selected
    if sel_mask.any():
        fig.add_trace(go.Scattergl(
            x=x_vals[sel_mask], y=y_vals[sel_mask],
            mode="markers",
            marker=dict(size=9, color="#EF553B", line=dict(width=2, color="black")),
            name="选中芯片",
            customdata=merged.loc[sel_mask, ["die_index", "head", "site"]].values,
            hovertemplate=(
                "Die %{customdata[0]} | H%{customdata[1]} S%{customdata[2]}<br>"
                f"{test_name}: %{{y:.3f}}<extra></extra>"
            ),
        ))

    # Extract LSL/USL
    y_range = None
    lsl_val = None
    usl_val = None
    if lsl is not None and len(lsl) > 0:
        lsl_nonan = lsl[~np.isnan(lsl)]
        if len(lsl_nonan) > 0:
            lsl_val = lsl_nonan[0]
    if usl is not None and len(usl) > 0:
        usl_nonan = usl[~np.isnan(usl)]
        if len(usl_nonan) > 0:
            usl_val = usl_nonan[0]

    if view_mode == "normal":
        if lsl_val is not None and usl_val is not None and usl_val > lsl_val:
            spec_range = usl_val - lsl_val
            margin = spec_range * 0.2
            y_range = [lsl_val - margin, usl_val + margin]

    elif view_mode == "minmax":
        data_y = y_vals[has_data & ~np.isnan(y_vals)]
        if len(data_y) > 0:
            y_min = data_y.min()
            y_max = data_y.max()
            data_range = y_max - y_min
            margin = data_range * 0.2
            y_range = [y_min - margin, y_max + margin]
            fig.add_hline(y=y_min, line_dash="dot", line_color="#2CA02C",
                          annotation_text=f"Min={y_min:.3f}")
            fig.add_hline(y=y_max, line_dash="dot", line_color="#2CA02C",
                          annotation_text=f"Max={y_max:.3f}")

    elif view_mode == "bin1":
        if lsl_val is not None and usl_val is not None and usl_val > lsl_val:
            spec_range = usl_val - lsl_val
            margin = spec_range * 0.05
            y_range = [lsl_val - margin, usl_val + margin]

    if lsl_val is not None:
        fig.add_hline(y=lsl_val, line_dash="dash", line_color="red",
                      annotation_text=f"LSL={lsl_val:.3f}")
    if usl_val is not None:
        fig.add_hline(y=usl_val, line_dash="dash", line_color="red",
                      annotation_text=f"USL={usl_val:.3f}")

    fig.update_layout(
        xaxis_title=x_label,
        yaxis_title=test_name,
        height=1080,
        margin=dict(l=20, r=20, t=20, b=20),
        hovermode="closest",
        clickmode="event+select",
    )
    fig.update_xaxes(range=[-0.5, len(die) - 0.5])
    if y_range is not None:
        fig.update_yaxes(range=y_range)
    return fig


def create_pareto_chart(
    die_df: pd.DataFrame,
    bin_labels: Optional[Dict[int, str]] = None,
    selected_bin: Optional[int] = None,
) -> go.Figure:
    if die_df.empty:
        return go.Figure()

    bin_counts = die_df["hard_bin"].value_counts().sort_values(ascending=False)
    total = bin_counts.sum()
    cumulative = bin_counts.cumsum() / total * 100

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    colors = ["#636EFA"] * len(bin_counts)
    if selected_bin is not None:
        for i, b in enumerate(bin_counts.index):
            if b == selected_bin:
                colors[i] = "#EF553B"

    fig.add_trace(
        go.Bar(
            x=[f"BIN {int(b)}" for b in bin_counts.index],
            y=bin_counts.values,
            name="芯片数",
            marker_color=colors,
            customdata=bin_counts.index.values,
            hovertemplate="%{x}: %{y} 颗<extra></extra>",
        ),
        secondary_y=False,
    )

    fig.add_trace(
        go.Scatter(
            x=[f"BIN {int(b)}" for b in bin_counts.index],
            y=cumulative.values,
            name="累计百分比",
            mode="lines+markers",
            marker=dict(size=8, color="red"),
            line=dict(color="red", width=2),
            hovertemplate="累计: %{y:.1f}%<extra></extra>",
        ),
        secondary_y=True,
    )

    fig.update_layout(
        title="BIN Pareto 分析",
        height=1080,
        margin=dict(l=20, r=20, t=40, b=20),
        hovermode="closest",
        clickmode="event+select",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_yaxes(title_text="芯片数", secondary_y=False)
    fig.update_yaxes(title_text="累计百分比 (%)", secondary_y=True, range=[0, 105])
    fig.update_xaxes(tickangle=0)
    return fig


def create_cpk_cards(cpk_df: pd.DataFrame, threshold: float = 1.33) -> go.Figure:
    if cpk_df.empty:
        return go.Figure()

    cpk_df = cpk_df.copy()
    cpk_df["color"] = cpk_df["cpk"].apply(
        lambda x: "#FF4D4F" if x < threshold else ("#FAAD14" if x < threshold * 1.2 else "#52C41A")
    )

    fig = go.Figure()

    for i, row in cpk_df.iterrows():
        fig.add_trace(go.Bar(
            x=[row["test_name"]],
            y=[max(row["cpk"], 0)],
            name=row["test_name"],
            marker_color=row["color"],
            customdata=[[row["cpk"], row["ppk"], row["n"], row["lsl"], row["usl"], row["mean"]]],
            hovertemplate=(
                f"{row['test_name']}<br>"
                f"Cpk: %{{customdata[0]:.3f}}<br>"
                f"Ppk: %{{customdata[1]:.3f}}<br>"
                f"N: %{{customdata[2]}}<br>"
                f"LSL: %{{customdata[3]:.3f}}<br>"
                f"USL: %{{customdata[4]:.3f}}<br>"
                f"Mean: %{{customdata[5]:.3f}}<extra></extra>"
            ),
        ))

    fig.add_hline(y=threshold, line_dash="dash", line_color="red",
                  annotation_text=f"阈值={threshold}")

    fig.update_layout(
        title=f"Cpk / Ppk 报告 (阈值: {threshold})",
        height=300,
        margin=dict(l=20, r=20, t=40, b=80),
        barmode="group",
        xaxis_tickangle=-45,
        hovermode="closest",
    )
    fig.update_yaxes(title_text="Cpk")
    return fig


def create_test_item_table(die_df: pd.DataFrame, test_df: pd.DataFrame, selected_dies: Optional[List[int]] = None) -> go.Figure:
    if not selected_dies or len(selected_dies) > 1:
        fig = go.Figure()
        fig.update_layout(
            title="选中芯片测试项详情",
            height=300,
            margin=dict(l=20, r=20, t=40, b=20),
        )
        return fig

    die_idx = selected_dies[0]
    die_row = die_df[die_df["die_index"] == die_idx]
    if die_row.empty:
        return go.Figure()

    die_tests = test_df[test_df["die_index"] == die_idx].copy()
    if die_tests.empty:
        return go.Figure()

    die_tests["Result"] = die_tests.apply(
        lambda r: "PASS" if (r["low_limit"] is None or r["high_limit"] is None or
                              r["low_limit"] <= r["result"] <= r["high_limit"])
        else "FAIL", axis=1
    )

    fig = go.Figure(data=[go.Table(
        header=dict(
            values=["测试项", "测试值", "LSL", "USL", "结果", "单位"],
            fill_color="#1E90FF",
            font=dict(color="white", size=11),
            align="center",
            height=28,
        ),
        cells=dict(
            values=[
                die_tests["test_name"],
                die_tests["result"].round(4),
                die_tests["low_limit"].fillna("-").apply(lambda x: f"{x:.4f}" if isinstance(x, (int, float)) else x),
                die_tests["high_limit"].fillna("-").apply(lambda x: f"{x:.4f}" if isinstance(x, (int, float)) else x),
                die_tests["Result"],
                die_tests["units"].fillna(""),
            ],
            fill_color=[
                ["#F5F5F5" if i % 2 else "white" for i in range(len(die_tests))]
            ],
            font=dict(size=10),
            align="center",
            height=24,
        )
    )])

    fig.update_layout(
        height=min(40 + len(die_tests) * 28, 400),
        margin=dict(l=5, r=5, t=5, b=5),
    )
    return fig
