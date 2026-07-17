from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from src.analysis import AnalysisOutput, PairedAnalysisOutput

WHITE_LAYOUT = {
    "paper_bgcolor": "#fbfdfc",
    "plot_bgcolor": "#fbfdfc",
    "font": {"color": "#173f3b"},
}


def build_analysis_figure(output: AnalysisOutput, max_line_points: int = 20_000) -> go.Figure:
    figure = go.Figure()
    if output.series:
        colors = ["#087f78", "#e05b49", "#2563eb", "#9467bd", "#d97706", "#059669"]
        for index, (label, x_values, y_values) in enumerate(output.series):
            step = max(1, len(x_values) // max_line_points)
            figure.add_scattergl(
                x=x_values[::step],
                y=y_values[::step],
                mode="lines",
                line={"color": colors[index % len(colors)], "width": 1.25},
                name=label,
            )
    elif output.kind == "bar":
        figure.add_bar(x=output.x, y=output.y, marker_color="#0f766e")
    else:
        step = max(1, len(output.x) // max_line_points)
        figure.add_scattergl(
            x=output.x[::step],
            y=output.y[::step],
            mode="lines",
            line={"color": "#0f766e", "width": 1.4},
        )
    figure.update_layout(
        title=output.title,
        xaxis_title=output.x_label,
        yaxis_title=output.y_label,
        height=680,
        margin={"l": 55, "r": 25, "t": 65, "b": 50},
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
        **WHITE_LAYOUT,
        xaxis={"gridcolor": "#dce7e5", "zerolinecolor": "#bdcfcc"},
        yaxis={"gridcolor": "#dce7e5", "zerolinecolor": "#bdcfcc"},
    )
    return figure


def build_paired_figure(output: PairedAnalysisOutput, max_points: int = 12_000) -> go.Figure:
    if output.kind in {"paired_normalized_fft", "paired_absolute_fft"}:
        figure = make_subplots(
            rows=3,
            cols=4,
            subplot_titles=[panel.label for panel in output.panels],
            horizontal_spacing=0.055,
            vertical_spacing=0.11,
        )
        for index, panel in enumerate(output.panels):
            row, column = divmod(index, 4)
            step = max(1, len(panel.x) // max_points)
            for values, color, name in (
                (panel.noarc, "#2563eb", "无弧"),
                (panel.arc, "#dc2626", "有弧"),
            ):
                figure.add_scattergl(
                    x=panel.x[::step],
                    y=values[::step],
                    mode="lines",
                    line={"color": color, "width": 1.0},
                    name=name,
                    legendgroup=name,
                    showlegend=index == 0,
                    row=row + 1,
                    col=column + 1,
                )
        figure.update_xaxes(title_text="频率 (Hz)", gridcolor="#dce7e5")
        figure.update_yaxes(title_text=output.y_label, gridcolor="#dce7e5")
        if output.kind == "paired_normalized_fft":
            maximum = max(10.0, float(output.panels[0].x[-1]))
            figure.update_xaxes(type="log", range=[1.0, float(np.log10(maximum))])
            figure.update_yaxes(range=[-190, 10])
            for row in range(1, 4):
                for column in range(1, 5):
                    for frequency in (3000, 500000):
                        figure.add_vline(
                            x=frequency,
                            line_dash="dot",
                            line_color="#94a3b8",
                            opacity=0.5,
                            row=row,
                            col=column,
                        )
        height = 870
    elif output.kind == "paired_wpt_ratio":
        figure = go.Figure()
        for panel in output.panels:
            figure.add_scatter(
                x=panel.x,
                y=panel.arc,
                mode="lines+markers",
                marker={"size": 4},
                line={"width": 1.4},
                name=panel.label,
            )
        figure.add_hline(y=0, line_dash="dot", line_color="#64748b")
        figure.add_hline(y=3, line_dash="dash", line_color="#dc2626")
        figure.update_xaxes(title_text=output.x_label, gridcolor="#dce7e5")
        figure.update_yaxes(title_text=output.y_label, gridcolor="#dce7e5")
        height = 680
    else:
        figure = make_subplots(rows=1, cols=2, subplot_titles=["有弧", "无弧"], shared_yaxes=True)
        for panel in output.panels:
            figure.add_scatter(
                x=panel.x,
                y=panel.arc,
                mode="lines+markers",
                marker={"size": 3},
                line={"width": 1.2},
                name=panel.label,
                legendgroup=panel.label,
                row=1,
                col=1,
            )
            figure.add_scatter(
                x=panel.x,
                y=panel.noarc,
                mode="lines+markers",
                marker={"size": 3},
                line={"width": 1.2},
                name=panel.label,
                legendgroup=panel.label,
                showlegend=False,
                row=1,
                col=2,
            )
        figure.update_xaxes(title_text=output.x_label, gridcolor="#dce7e5")
        figure.update_yaxes(title_text=output.y_label, gridcolor="#dce7e5")
        height = 720

    figure.update_layout(
        title=output.title,
        height=height,
        margin={"l": 45, "r": 20, "t": 75, "b": 45},
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
        **WHITE_LAYOUT,
    )
    return figure


def render_analysis_output(output: AnalysisOutput, show_table: bool = True) -> None:
    figure = build_analysis_figure(output)
    st.plotly_chart(figure, width="stretch")
    if show_table:
        st.dataframe(output.table, width="stretch", hide_index=True)


def render_paired_output(output: PairedAnalysisOutput, show_table: bool = True) -> None:
    st.plotly_chart(build_paired_figure(output), width="stretch")
    if show_table:
        st.dataframe(output.table, width="stretch", hide_index=True)
