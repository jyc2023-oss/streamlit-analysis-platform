from __future__ import annotations

from typing import Any

from streamlit.components.v2 import component

_CLICK_BRIDGE_JS = r"""
export default function(component) {
    const { data, setTriggerValue } = component;
    let plot = null;
    let disposed = false;

    const clickHandler = (event) => {
        const point = event?.points?.[0];
        if (!point || point.x === undefined || point.x === null) return;
        const customdata = Array.isArray(point.customdata)
            ? point.customdata
            : (point.customdata === undefined ? [] : [point.customdata]);
        setTriggerValue("clicked", {
            x: Number(point.x),
            y: Number(point.y),
            curve_number: Number(point.curveNumber ?? -1),
            point_number: Number(point.pointNumber ?? point.pointIndex ?? -1),
            customdata,
            nonce: `${Date.now()}-${Math.random()}`,
        });
    };

    const attach = () => {
        if (disposed) return;
        const selector = `.st-key-${CSS.escape(data.chartKey)} .js-plotly-plot`;
        const nextPlot = document.querySelector(selector);
        if (!nextPlot || nextPlot === plot || typeof nextPlot.on !== "function") return;
        if (plot && typeof plot.removeListener === "function") {
            plot.removeListener("plotly_click", clickHandler);
        }
        plot = nextPlot;
        plot.on("plotly_click", clickHandler);
        plot.style.cursor = "crosshair";
    };

    attach();
    const timer = window.setInterval(attach, 100);
    return () => {
        disposed = true;
        window.clearInterval(timer);
        if (plot && typeof plot.removeListener === "function") {
            plot.removeListener("plotly_click", clickHandler);
        }
    };
}
"""

_plotly_click_bridge = component(
    "plotly_direct_click_bridge",
    html='<span class="plotly-click-bridge"></span>',
    css=".plotly-click-bridge { display: none; height: 0; }",
    js=_CLICK_BRIDGE_JS,
)


def capture_plotly_click(chart_key: str, key: str) -> Any:
    """Capture regular Plotly click events from the chart identified by its Streamlit key."""
    return _plotly_click_bridge(
        data={"chartKey": chart_key},
        key=key,
        on_clicked_change=lambda: None,
    )
