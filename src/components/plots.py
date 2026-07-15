from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from src.analysis import AnalysisOutput


def render_analysis_output(output: AnalysisOutput) -> None:
    figure = go.Figure()
    if output.kind == "bar":
        figure.add_bar(x=output.x, y=output.y, marker_color="#2563eb")
    else:
        figure.add_scattergl(x=output.x, y=output.y, mode="lines", line={"color": "#2563eb"})
    figure.update_layout(
        title=output.title,
        xaxis_title=output.x_label,
        yaxis_title=output.y_label,
        height=520,
        margin={"l": 40, "r": 20, "t": 60, "b": 40},
        hovermode="x unified",
    )
    st.plotly_chart(figure, use_container_width=True)
    st.dataframe(output.table, use_container_width=True, hide_index=True)
