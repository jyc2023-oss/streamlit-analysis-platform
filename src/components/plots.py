from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from src.analysis import AnalysisOutput


def build_analysis_figure(output: AnalysisOutput, max_line_points: int = 20_000) -> go.Figure:
    figure = go.Figure()
    if output.kind == "bar":
        figure.add_bar(x=output.x, y=output.y, marker_color="#2563eb")
    else:
        step = max(1, len(output.x) // max_line_points)
        figure.add_scattergl(
            x=output.x[::step],
            y=output.y[::step],
            mode="lines",
            line={"color": "#38bdf8", "width": 1.4},
        )
    figure.update_layout(
        title=output.title,
        xaxis_title=output.x_label,
        yaxis_title=output.y_label,
        height=610,
        margin={"l": 55, "r": 25, "t": 65, "b": 50},
        hovermode="x unified",
        paper_bgcolor="#08111f",
        plot_bgcolor="#0b1728",
        font={"color": "#cbd5e1"},
        xaxis={"gridcolor": "rgba(148,163,184,.14)", "zerolinecolor": "rgba(148,163,184,.3)"},
        yaxis={"gridcolor": "rgba(148,163,184,.14)", "zerolinecolor": "rgba(148,163,184,.3)"},
    )
    return figure


def render_analysis_output(output: AnalysisOutput, show_table: bool = True) -> None:
    figure = build_analysis_figure(output)
    st.plotly_chart(figure, width="stretch")
    if show_table:
        st.dataframe(output.table, width="stretch", hide_index=True)
