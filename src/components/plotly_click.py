from __future__ import annotations

from collections.abc import Callable
from typing import Any

from streamlit.components.v2 import component

_CYCLE_PICKER_HTML = r"""
<div class="cycle-picker">
  <div class="cycle-picker__toolbar">
    <span class="cycle-picker__label">点击归类</span>
    <button type="button" data-mode="noarc">无弧</button>
    <button type="button" data-mode="arc">有弧</button>
    <button type="button" data-mode="remove">取消</button>
    <span class="cycle-picker__status" data-role="status"></span>
    <button type="button" data-action="clear-current">清空当前类别</button>
    <button type="button" data-action="clear-all">全部清空</button>
    <button type="button" class="cycle-picker__apply" data-action="apply">
      确认并分析
    </button>
  </div>
  <div class="cycle-picker__message" data-role="message">
    可先缩放波形，再连续点击多个周波；点选过程不会刷新页面。
  </div>
</div>
"""

_CYCLE_PICKER_CSS = r"""
.cycle-picker {
  color: #173f3b;
  font-family: "Segoe UI Variable Text", "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
  padding: 0.2rem 0 0.55rem;
}
.cycle-picker__toolbar {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
}
.cycle-picker__label { font-weight: 650; margin-right: 0.1rem; }
.cycle-picker button {
  background: #fbfdfc;
  border: 1px solid #c3d2cf;
  border-radius: 0.58rem;
  color: #405c59;
  cursor: pointer;
  font-size: 0.9rem;
  font-weight: 600;
  line-height: 1.2;
  padding: 0.48rem 0.78rem;
  transition: border-color 180ms ease, box-shadow 180ms ease, transform 120ms ease;
}
.cycle-picker button:hover {
  border-color: #0f766e;
  box-shadow: 0 0.45rem 1rem rgba(15, 118, 110, 0.11);
  transform: translateY(-1px);
}
.cycle-picker button:active { transform: translateY(1px) scale(0.99); }
.cycle-picker button:focus-visible {
  outline: 3px solid rgba(15, 118, 110, 0.2);
  outline-offset: 2px;
}
.cycle-picker button[data-active="true"][data-mode="noarc"] {
  background: #2563eb; border-color: #2563eb; color: #fff;
}
.cycle-picker button[data-active="true"][data-mode="arc"] {
  background: #dc2626; border-color: #dc2626; color: #fff;
}
.cycle-picker button[data-active="true"][data-mode="remove"] {
  background: #405c59; border-color: #405c59; color: #fff;
}
.cycle-picker__status {
  color: #405c59;
  font-size: 0.9rem;
  font-weight: 650;
  margin: 0 0.35rem;
}
.cycle-picker button.cycle-picker__apply {
  background: #0f766e;
  border-color: #0f766e;
  color: #fff;
  font-weight: 650;
  margin-left: auto;
}
.cycle-picker button.cycle-picker__apply:disabled {
  background: #d8e3e1;
  border-color: #d8e3e1;
  color: #718582;
  cursor: not-allowed;
}
.cycle-picker__message {
  color: #607474;
  font-size: 0.86rem;
  min-height: 1.25rem;
  padding-top: 0.45rem;
}
.cycle-picker__message[data-kind="warning"] { color: #b45309; }
.cycle-picker__message[data-kind="ready"] { color: #047857; }
"""

_CYCLE_PICKER_JS = r"""
export default function(component) {
    const { data, parentElement, setTriggerValue } = component;
    const root = parentElement.querySelector(".cycle-picker");
    const status = root.querySelector('[data-role="status"]');
    const message = root.querySelector('[data-role="message"]');
    const applyButton = root.querySelector('[data-action="apply"]');
    const modeButtons = [...root.querySelectorAll("[data-mode]")];
    const validStarts = [...new Set((data.starts ?? []).map(Number))];
    const validSet = new Set(validStarts);
    const maximum = Number(data.maximum);
    const cyclePoints = Number(data.cyclePoints);
    const sampleRate = Number(data.sampleRate);
    const singleMode = Boolean(data.singleMode);
    const axisCount = Math.max(1, Number(data.axisCount ?? 4));
    let noarc = [...new Set((data.initialNoarc ?? []).map(Number))]
        .filter(value => validSet.has(value)).slice(0, maximum);
    let arc = singleMode ? [] : [...new Set((data.initialArc ?? []).map(Number))]
        .filter(value => validSet.has(value) && !noarc.includes(value)).slice(0, maximum);
    let mode = "noarc";
    let plot = null;
    let overlay = null;
    let disposed = false;
    let dirty = false;
    let submitting = false;
    let drawFrame = null;
    let lastPlotlyClick = 0;

    if (singleMode) {
        root.querySelector(".cycle-picker__label").textContent = "周波选择";
        const noarcButton = root.querySelector('[data-mode="noarc"]');
        const arcButton = root.querySelector('[data-mode="arc"]');
        noarcButton.textContent = "选择";
        arcButton.hidden = true;
    }

    const setMessage = (text, kind = "") => {
        message.textContent = text;
        message.dataset.kind = kind;
    };

    const updateControls = () => {
        modeButtons.forEach(button => {
            button.dataset.active = String(button.dataset.mode === mode);
        });
        status.textContent = singleMode
            ? `已选择 ${noarc.length}/${maximum}`
            : `无弧 ${noarc.length}/${maximum} · 有弧 ${arc.length}/${maximum}`;
        const ready = singleMode
            ? noarc.length === maximum
            : noarc.length === maximum && arc.length === maximum;
        applyButton.textContent = ready ? "确认并分析" : "保存当前选择";
        applyButton.disabled = submitting || !dirty;
        if (ready) {
            setMessage("选择已完成。可继续调整，或点击“确认并分析”提交一次。", "ready");
        }
    };

    const removeOverlay = () => {
        if (plot) {
            plot.querySelectorAll("[data-cycle-picker-overlay]").forEach(layer => layer.remove());
        } else if (overlay) overlay.remove();
        overlay = null;
    };

    const addBand = (layer, start, color, axisIndex) => {
        const layout = plot?._fullLayout;
        const xaxis = layout?.[axisIndex === 1 ? "xaxis" : `xaxis${axisIndex}`];
        const yaxis = layout?.[axisIndex === 1 ? "yaxis" : `yaxis${axisIndex}`];
        if (!xaxis || !yaxis || typeof xaxis.l2p !== "function") return;
        const leftValue = start / sampleRate;
        const rightValue = (start + cyclePoints) / sampleRate;
        const left = xaxis._offset + xaxis.l2p(leftValue);
        const right = xaxis._offset + xaxis.l2p(rightValue);
        if (!Number.isFinite(left) || !Number.isFinite(right)) return;

        const band = document.createElement("div");
        const visibleLeft = Math.min(left, right);
        const visibleWidth = Math.max(3, Math.abs(right - left));
        Object.assign(band.style, {
            position: "absolute",
            pointerEvents: "none",
            left: `${visibleLeft}px`,
            top: `${yaxis._offset}px`,
            width: `${visibleWidth}px`,
            height: `${yaxis._length}px`,
            background: color,
            borderLeft: "1px solid rgba(15, 23, 42, 0.35)",
            borderRight: "1px solid rgba(15, 23, 42, 0.35)",
            boxSizing: "border-box",
        });
        const center = document.createElement("div");
        Object.assign(center.style, {
            position: "absolute",
            left: "50%",
            top: "0",
            bottom: "0",
            borderLeft: "2px dashed currentColor",
            color: color.includes("37, 99, 235") ? "#1d4ed8" : "#b91c1c",
        });
        band.appendChild(center);
        layer.appendChild(band);
    };

    const drawNow = () => {
        drawFrame = null;
        if (!plot || !plot.isConnected || !plot._fullLayout) return;
        removeOverlay();
        overlay = document.createElement("div");
        overlay.dataset.cyclePickerOverlay = "true";
        Object.assign(overlay.style, {
            position: "absolute",
            inset: "0",
            overflow: "hidden",
            pointerEvents: "none",
            zIndex: "5",
        });
        plot.style.position = "relative";
        plot.appendChild(overlay);
        for (const start of noarc) {
            for (let axis = 1; axis <= axisCount; axis += 1) {
                addBand(overlay, start, "rgba(37, 99, 235, 0.24)", axis);
            }
        }
        for (const start of arc) {
            for (let axis = 1; axis <= axisCount; axis += 1) {
                addBand(overlay, start, "rgba(220, 38, 38, 0.24)", axis);
            }
        }
    };

    const scheduleDraw = () => {
        if (drawFrame !== null) window.cancelAnimationFrame(drawFrame);
        drawFrame = window.requestAnimationFrame(drawNow);
    };

    const nearestStart = (x) => {
        if (!validStarts.length || !Number.isFinite(x)) return null;
        const clickedSample = x * sampleRate;
        let nearest = validStarts[0];
        let distance = Math.abs(nearest + cyclePoints / 2 - clickedSample);
        for (let index = 1; index < validStarts.length; index += 1) {
            const candidate = validStarts[index];
            const candidateDistance = Math.abs(candidate + cyclePoints / 2 - clickedSample);
            if (candidateDistance < distance) {
                nearest = candidate;
                distance = candidateDistance;
            }
        }
        return nearest;
    };

    const applyStart = (start) => {
        if (start === null) return;
        if (mode === "remove") {
            noarc = noarc.filter(value => value !== start);
            arc = arc.filter(value => value !== start);
            setMessage("已取消该周波。可继续点选，页面不会刷新。");
        } else {
            const current = mode === "noarc" ? noarc : arc;
            const other = mode === "noarc" ? arc : noarc;
            const label = mode === "noarc" ? "无弧" : "有弧";
            if (other.includes(start)) {
                setMessage("该周波已属于另一类别，请先选择“取消”后再点击。", "warning");
                return;
            }
            if (current.includes(start)) {
                const updated = current.filter(value => value !== start);
                if (mode === "noarc") noarc = updated;
                else arc = updated;
                setMessage(`已从${label}中取消该周波。`);
            } else if (current.length >= maximum) {
                setMessage(`${label}已经选满 ${maximum} 个周波，请先取消一个。`, "warning");
                return;
            } else {
                current.push(start);
                setMessage(`已加入${label}，可继续点击下一个周波。`);
            }
        }
        dirty = true;
        updateControls();
        scheduleDraw();
    };

    const clickHandler = (event) => {
        lastPlotlyClick = performance.now();
        const point = event?.points?.[0];
        applyStart(nearestStart(Number(point?.x)));
    };

    const nativeClickHandler = (event) => {
        if (event.button !== 0 || event.target.closest(".modebar")) return;
        window.setTimeout(() => {
            if (!plot || performance.now() - lastPlotlyClick < 180) return;
            const xaxis = plot._fullLayout?.xaxis;
            if (!xaxis || typeof xaxis.p2l !== "function") return;
            const bounds = plot.getBoundingClientRect();
            const pixel = event.clientX - bounds.left - xaxis._offset;
            applyStart(nearestStart(xaxis.p2l(pixel)));
        }, 80);
    };

    const relayoutHandler = () => scheduleDraw();
    const afterPlotHandler = () => scheduleDraw();

    const detachPlot = () => {
        if (plot && typeof plot.removeListener === "function") {
            plot.removeListener("plotly_click", clickHandler);
            plot.removeListener("plotly_relayout", relayoutHandler);
            plot.removeListener("plotly_afterplot", afterPlotHandler);
            plot.removeEventListener("click", nativeClickHandler);
        }
        removeOverlay();
        plot = null;
    };

    const attach = () => {
        if (disposed) return;
        const selector = `.st-key-${CSS.escape(data.chartKey)} .js-plotly-plot`;
        const nextPlot = document.querySelector(selector);
        if (!nextPlot || nextPlot === plot || typeof nextPlot.on !== "function") return;
        detachPlot();
        plot = nextPlot;
        plot.on("plotly_click", clickHandler);
        plot.on("plotly_relayout", relayoutHandler);
        plot.on("plotly_afterplot", afterPlotHandler);
        plot.addEventListener("click", nativeClickHandler);
        plot.style.cursor = "crosshair";
        scheduleDraw();
    };

    modeButtons.forEach(button => {
        button.onclick = () => {
            mode = button.dataset.mode;
            updateControls();
        };
    });

    const submitSelection = () => {
        submitting = true;
        applyButton.disabled = true;
        applyButton.textContent = "正在提交…";
        setTriggerValue("applied", {
            noarc: [...noarc],
            arc: [...arc],
            nonce: `${Date.now()}-${Math.random()}`,
        });
    };

    root.querySelector('[data-action="clear-current"]').onclick = () => {
        if (mode === "remove") {
            noarc = [];
            arc = [];
        } else if (mode === "noarc") noarc = [];
        else arc = [];
        dirty = true;
        setMessage("正在清空已保存的选择…", "");
        updateControls();
        removeOverlay();
        submitSelection();
    };
    root.querySelector('[data-action="clear-all"]').onclick = () => {
        noarc = [];
        arc = [];
        dirty = true;
        setMessage("正在清空全部已保存选择…", "");
        updateControls();
        removeOverlay();
        submitSelection();
    };
    applyButton.onclick = () => {
        if (!dirty || submitting) return;
        submitSelection();
    };

    const registry = window.__streamlitCyclePickerRegistry ??= new Map();
    const previousDispose = registry.get(data.chartKey);
    if (previousDispose) previousDispose();

    updateControls();
    attach();
    const timer = window.setInterval(attach, 150);
    window.addEventListener("resize", scheduleDraw);
    const dispose = () => {
        if (disposed) return;
        disposed = true;
        window.clearInterval(timer);
        window.removeEventListener("resize", scheduleDraw);
        if (drawFrame !== null) window.cancelAnimationFrame(drawFrame);
        detachPlot();
    };
    registry.set(data.chartKey, dispose);
    return () => {
        if (registry.get(data.chartKey) === dispose) registry.delete(data.chartKey);
        dispose();
    };
}
"""

_cycle_picker = component(
    "plotly_cycle_selection_picker",
    html=_CYCLE_PICKER_HTML,
    css=_CYCLE_PICKER_CSS,
    js=_CYCLE_PICKER_JS,
)


def render_cycle_picker(
    chart_key: str,
    starts: list[int],
    cycle_points: int,
    sample_rate: float,
    initial_noarc: list[int],
    initial_arc: list[int],
    maximum: int,
    key: str,
    on_applied_change: Callable[[], None],
    single_mode: bool = False,
    axis_count: int = 4,
) -> Any:
    """Render a no-rerun browser-side picker for detected waveform cycles."""
    return _cycle_picker(
        data={
            "chartKey": chart_key,
            "starts": starts,
            "cyclePoints": cycle_points,
            "sampleRate": sample_rate,
            "initialNoarc": initial_noarc,
            "initialArc": initial_arc,
            "maximum": maximum,
            "singleMode": single_mode,
            "axisCount": axis_count,
        },
        key=key,
        on_applied_change=on_applied_change,
        width="stretch",
        height="content",
    )
