from __future__ import annotations

import hashlib
import html
import json
import math
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from src.analysis import (
    ANALYSIS_TYPES,
    PAIRED_ANALYSIS_TYPES,
    AnalysisOutput,
    PairedChannelCycles,
    detect_cycle_starts,
    run_analysis,
    run_paired_analysis,
)
from src.analysis.selection import normalize_cycle_selection
from src.auth.ui import require_user
from src.components.plotly_click import render_cycle_picker
from src.components.plots import render_analysis_output, render_paired_output
from src.config import get_settings
from src.db import init_db
from src.services.datasets import (
    dataset_catalog_revision,
    downsample,
    filter_datasets_by_folder,
    folder_choices,
    hydrate_dataset_metadata,
    list_datasets,
    load_channel,
    scan_datasets,
)
from src.services.jobs import (
    create_job,
    mark_failed,
    mark_running,
    render_figure_bytes,
    save_job_result,
)
from src.ui import render_page_intro

CHANNEL_LABELS_8 = ["5m", "10m", "20m", "40m", "80m", "120m", "160m", "背景支路"]
CHANNEL_LABELS_2 = ["电弧发生处", "2m主干"]
ALL_ANALYSIS_TYPES = {**ANALYSIS_TYPES, **PAIRED_ANALYSIS_TYPES}
IS_ARC_PAGE = bool(globals().get("ARC_PAGE_MODE", False))
PAGE_ANALYSIS_TYPES = (
    {"arc_features": ALL_ANALYSIS_TYPES["arc_features"]}
    if IS_ARC_PAGE
    else {
        key: value
        for key, value in ALL_ANALYSIS_TYPES.items()
        if key != "arc_features"
    }
)
USE_CURRENT_FOLDER = "__USE_CURRENT_FOLDER__"
FFT_CYCLE_OPTIONS = (1, 5)
CYCLE_SELECTION_TYPES = {"fft"}


@st.cache_data(show_spinner=False, ttl=600)
def compute_preview(
    dataset_id: int,
    modified_at: str,
    channel: str,
    start: int,
    end: int,
    sample_rate: float,
    analysis_type: str,
    parameters_json: str,
):
    del modified_at
    values, _ = load_channel(dataset_id, channel, start, end)
    parameters = json.loads(parameters_json)
    if analysis_type == "waveform":
        parameters["max_output_points"] = 40_000
        parameters["time_offset"] = start / sample_rate
    return run_analysis(analysis_type, values, sample_rate, parameters)


@st.cache_data(show_spinner=False, ttl=600)
def load_fft_cycle_context(
    channel_refs: tuple[tuple[int, str, str, str], ...],
    sample_rate: float,
    start: int,
    end: int,
) -> dict[str, Any]:
    reference_id, _modified_at, reference_channel, _label = channel_refs[0]
    reference, _ = load_channel(reference_id, reference_channel, start, end)
    relative_starts = detect_cycle_starts(reference, sample_rate, len(reference))
    traces = []
    for dataset_id, _modified_at, channel, label in channel_refs:
        values = (
            reference
            if (dataset_id, channel) == (reference_id, reference_channel)
            else load_channel(dataset_id, channel, start, end)[0]
        )
        indices, sampled = downsample(values, 40_000)
        traces.append(
            {
                "label": label,
                "time": (start + indices).astype(np.float64) / sample_rate,
                "values": sampled,
            }
        )
    return {
        "starts": [start + int(item) for item in relative_starts],
        "cycle_points": int(round(sample_rate / 50.0)),
        "traces": traces,
    }


@st.cache_data(show_spinner=False, ttl=600)
def compute_fft_cycle_preview(
    channel_refs: tuple[tuple[int, str, str, str], ...],
    sample_rate: float,
    starts: tuple[int, ...],
    cycle_points: int,
    parameters_json: str,
):
    parameters = json.loads(parameters_json)
    series = []
    tables = []
    first_output = None
    for dataset_id, _modified_at, channel, label in channel_refs:
        cycles = [
            load_channel(dataset_id, channel, start, start + cycle_points)[0]
            for start in starts
        ]
        output = run_analysis("fft", np.concatenate(cycles), sample_rate, parameters)
        first_output = first_output or output
        series.append((label, output.x, output.y))
        tables.append(
            pd.DataFrame(
                {"通道": label, "频率_Hz": output.x, "幅值": output.y}
            )
        )
    if first_output is None:
        raise ValueError("没有可用于 FFT 的通道。")
    return AnalysisOutput(
        f"{len(starts)} 周波多通道 FFT 幅值谱",
        first_output.x,
        first_output.y,
        "频率 (Hz)",
        "幅值",
        "line",
        pd.concat(tables, ignore_index=True),
        series,
    )


@st.cache_data(show_spinner=False, ttl=600)
def compute_arc_feature_preview(
    dataset_id: int,
    modified_at: str,
    channel: str,
    sample_rate: float,
    starts: tuple[int, ...],
    cycle_points: int,
):
    del modified_at
    cycles = [
        load_channel(dataset_id, channel, start, start + cycle_points)[0] for start in starts
    ]
    return run_analysis(
        "arc_features",
        np.concatenate(cycles),
        sample_rate,
        {"cycle_points": cycle_points},
    )


@st.cache_data(show_spinner=False, ttl=600)
def load_cycle_context(
    dataset_8_id: int,
    modified_8: str,
    dataset_2_id: int,
    modified_2: str,
    sample_rate: float,
    usable_samples: int,
) -> dict[str, Any]:
    del modified_8, modified_2
    reference, _ = load_channel(dataset_8_id, "CH07", 0, usable_samples)
    starts = detect_cycle_starts(reference, sample_rate, usable_samples)
    traces = []
    references = [
        (dataset_8_id, "CH07", "8CH · CH07 · 160m"),
        (dataset_8_id, "CH08", "8CH · CH08 · 背景支路"),
        (dataset_2_id, "CH01", "2CH · CH01 · 电弧发生处"),
        (dataset_2_id, "CH02", "2CH · CH02 · 2m主干"),
    ]
    for dataset_id, channel, label in references:
        values = (
            reference
            if (dataset_id, channel) == (dataset_8_id, "CH07")
            else load_channel(dataset_id, channel, 0, usable_samples)[0]
        )
        indices, sampled = downsample(values, 30_000)
        traces.append(
            {
                "label": label,
                "time": indices.astype(np.float64) / sample_rate,
                "values": sampled,
            }
        )
    return {
        "starts": starts,
        "cycle_points": int(round(sample_rate / 50.0)),
        "traces": traces,
    }


@st.cache_data(show_spinner=False, ttl=600)
def compute_paired_preview(
    dataset_8_id: int,
    modified_8: str,
    channels_8: tuple[str, ...],
    dataset_2_id: int,
    modified_2: str,
    channels_2: tuple[str, ...],
    sample_rate: float,
    noarc_starts: tuple[int, ...],
    arc_starts: tuple[int, ...],
    cycle_points: int,
    analysis_type: str,
    parameters_json: str,
):
    del modified_8, modified_2

    def cycles(dataset_id: int, channel: str, starts: tuple[int, ...]) -> list[np.ndarray]:
        return [
            load_channel(dataset_id, channel, start, start + cycle_points)[0] for start in starts
        ]

    paired_channels = []
    for group, dataset_id, channels, labels in (
        ("8CH", dataset_8_id, channels_8, CHANNEL_LABELS_8),
        ("2CH", dataset_2_id, channels_2, CHANNEL_LABELS_2),
    ):
        for index, channel in enumerate(channels):
            business_label = labels[index] if index < len(labels) else channel
            paired_channels.append(
                PairedChannelCycles(
                    label=f"{group}-{channel} {business_label}",
                    group=group,
                    channel=channel,
                    noarc_cycles=cycles(dataset_id, channel, noarc_starts),
                    arc_cycles=cycles(dataset_id, channel, arc_starts),
                )
            )
    return run_paired_analysis(
        analysis_type, paired_channels, sample_rate, json.loads(parameters_json)
    )


def choose_dataset(title: str, datasets: list[dict[str, Any]], key: str) -> dict | None:
    if not datasets:
        st.selectbox(title, ["未找到匹配文件"], disabled=True, key=f"{key}_empty")
        return None
    labels = {f"{item['name']}  ·  #{item['id']}": item for item in datasets}
    selected = st.selectbox(title, list(labels), key=key)
    item = labels[selected]
    safe_name = html.escape(item["name"])
    st.markdown(
        f'<div class="full-file-name" title="{safe_name}">{safe_name}</div>',
        unsafe_allow_html=True,
    )
    return item


def choose_dataset_folder(
    datasets: list[dict[str, Any]], key: str, max_levels: int = 12
) -> tuple[str, ...]:
    channel_counts = {int(item["metadata"].get("channels_count", 0)) for item in datasets}
    required_counts = {8, 2} if {8, 2}.issubset(channel_counts) else set()
    selected_parts: tuple[str, ...] = ()
    for level in range(max_levels):
        children = folder_choices(datasets, selected_parts, required_counts)
        if not children:
            break
        options = [*children]
        if selected_parts:
            options.append(USE_CURRENT_FOLDER)
        selected = st.selectbox(
            f"第 {level + 1} 级文件夹",
            options,
            format_func=lambda value: (
                "📂 在当前文件夹选择文件" if value == USE_CURRENT_FOLDER else f"📁 {value.strip()}"
            ),
            key=f"{key}_level_{level}",
        )
        if selected == USE_CURRENT_FOLDER:
            break
        selected_parts = (*selected_parts, selected)
    if selected_parts:
        breadcrumb = " / ".join(part.strip() for part in selected_parts)
        st.caption(f"当前位置：{breadcrumb}")
    return selected_parts


def channel_length(dataset: dict[str, Any], channel: str) -> int:
    shape = dataset["metadata"].get("shapes", {}).get(channel)
    if shape:
        return int(math.prod(shape))
    return int(dataset["metadata"].get("total_samples", 0))


def add_channel_options(
    options: dict[str, tuple[dict[str, Any], str]],
    dataset: dict[str, Any] | None,
    group: str,
    business_labels: list[str] | None = None,
) -> None:
    if dataset is None:
        return
    for index, channel in enumerate(dataset["metadata"].get("channels", [])):
        business_name = (
            business_labels[index]
            if business_labels is not None and index < len(business_labels)
            else channel
        )
        options[f"{group} · {channel} · {business_name}"] = (dataset, channel)


def build_cycle_selection_figure(
    context: dict[str, Any],
) -> go.Figure:
    figure = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.055)
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#9467bd"]
    for row, (trace, color) in enumerate(zip(context["traces"], colors, strict=True), 1):
        figure.add_scattergl(
            x=trace["time"],
            y=trace["values"],
            mode="lines",
            line={"color": color, "width": 0.8},
            name=trace["label"],
            row=row,
            col=1,
        )
        figure.update_yaxes(title_text=trace["label"], gridcolor="#dce7e5", row=row, col=1)
    figure.update_xaxes(title_text="时间 (s)", gridcolor="#dce7e5", row=4, col=1)
    figure.update_layout(
        title="周波手动选择（可先缩放，再连续点选；蓝色：无弧，红色：有弧）",
        height=700,
        margin={"l": 105, "r": 20, "t": 65, "b": 45},
        paper_bgcolor="#fbfdfc",
        plot_bgcolor="#fbfdfc",
        font={"color": "#173f3b"},
        hovermode="x unified",
        legend={"orientation": "h", "y": 1.02},
    )
    return figure


def build_fft_cycle_selection_figure(
    context: dict[str, Any], cycle_count: int
) -> go.Figure:
    figure = go.Figure()
    colors = ["#087f78", "#e05b49", "#2563eb", "#9467bd", "#d97706", "#059669"]
    for index, trace in enumerate(context["traces"]):
        figure.add_scattergl(
            x=trace["time"],
            y=trace["values"],
            mode="lines",
            line={"color": colors[index % len(colors)], "width": 0.9},
            name=trace["label"],
        )
    figure.update_xaxes(title_text="时间 (s)", gridcolor="#dce7e5")
    figure.update_yaxes(title_text="幅值", gridcolor="#dce7e5")
    figure.update_layout(
        title=f"FFT 周波选择（可先缩放，再连续点击 {cycle_count} 个周波）",
        height=470,
        margin={"l": 70, "r": 20, "t": 65, "b": 50},
        paper_bgcolor="#fbfdfc",
        plot_bgcolor="#fbfdfc",
        font={"color": "#173f3b"},
        hovermode="x",
        hoverdistance=-1,
        clickmode="event+select",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
    )
    return figure


def render_file_info(
    placeholder: Any, selected_8: dict[str, Any] | None, selected_2: dict[str, Any] | None
) -> None:
    with placeholder.container():
        st.divider()
        st.caption("当前配对数据")
        if selected_8:
            st.markdown("**8 通道文件**")
            st.markdown(
                f'<div class="file-info-name">{html.escape(selected_8["name"])}</div>',
                unsafe_allow_html=True,
            )
        if selected_2:
            st.markdown("**2 通道文件**")
            st.markdown(
                f'<div class="file-info-name">{html.escape(selected_2["name"])}</div>',
                unsafe_allow_html=True,
            )


init_db()
user = require_user()
settings = get_settings()

st.markdown(
    """
    <style>
      .screen-label {
        color:#173f3b; font-size:1.02rem; font-weight:700; letter-spacing:-.01em;
        margin-bottom:.65rem;
      }
      .channel-caption {color:#607474; font-size:.88rem; margin-top:-.4rem;}
      .full-file-name, .file-info-name {
        color:#607474; font-size:.78rem; line-height:1.45; overflow-wrap:anywhere;
        margin:-.25rem 0 .65rem;
      }
      [data-testid="stSelectbox"] div[data-baseweb="select"] > div {
        min-height:3.15rem; height:auto;
      }
      [role="listbox"] {
        overflow-x:scroll !important; overflow-y:auto !important;
        scrollbar-color:#789792 #e4ecea; scrollbar-gutter:stable; scrollbar-width:thin;
      }
      [role="listbox"]::-webkit-scrollbar {height:8px; width:8px;}
      [role="listbox"]::-webkit-scrollbar-track {
        background:#e4ecea; border-radius:999px;
      }
      [role="listbox"]::-webkit-scrollbar-thumb {
        background:#789792; border-radius:999px;
      }
      [role="listbox"] > * {
        min-width:64rem !important;
      }
      [role="option"] {
        min-width:64rem !important; width:max-content !important;
        max-width:none !important;
        white-space:nowrap !important;
      }
      [role="option"] * {
        max-width:none !important; overflow:visible !important;
        text-overflow:clip !important; white-space:nowrap !important;
        flex-shrink:0 !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

title_column, action_column = st.columns([5, 4], vertical_alignment="center")
with title_column:
    render_page_intro(
        "电弧识别工作台" if IS_ARC_PAGE else "数据分析工作台",
        (
            "进入数据文件夹后，自动使用116文件的CH1全量数据逐半波检测并给出文件夹结论。"
            if IS_ARC_PAGE
            else "选择算法、数据文件与通道，中央画布会同步更新，并可保存图像、数据和完整分析记录。"
        ),
    )
action_placeholder = action_column.empty()


@st.fragment(run_every="3s")
def watch_dataset_catalog() -> None:
    """Refresh the full workbench only when the background index actually changes."""
    revision = dataset_catalog_revision()
    state_key = "workbench_dataset_catalog_revision"
    previous = st.session_state.get(state_key)
    st.session_state[state_key] = revision
    if previous is not None and previous != revision:
        st.cache_data.clear()
        st.rerun(scope="app")


watch_dataset_catalog()

datasets = list_datasets(status="ready")
if not datasets:
    st.info("没有可分析的数据。请先到“数据浏览”页面刷新索引。")
    st.stop()

left_panel, screen_panel, right_panel = st.columns([1.15, 5.8, 2.0], gap="medium")

with left_panel:
    with st.container(border=True):
        st.markdown("#### 电弧识别" if IS_ARC_PAGE else "#### 分析方法")
        if IS_ARC_PAGE:
            analysis_type = "arc_features"
            st.markdown("⚡ **24维电弧特征识别**")
        else:
            analysis_type = st.radio(
                "选择分析方法",
                list(PAGE_ANALYSIS_TYPES),
                format_func=lambda key: PAGE_ANALYSIS_TYPES[key]["label"],
                label_visibility="collapsed",
                key="workbench_analysis_type",
            )
        definition = PAGE_ANALYSIS_TYPES[analysis_type]
        st.caption(definition["description"])
        st.divider()
        st.markdown("**操作提示**")
        st.caption("鼠标滚轮缩放，拖动选择区域；双击恢复完整视图。图表右上角可以直接截图。")

with right_panel:
    with st.container(border=True):
        st.markdown("#### 分析文件")
        st.caption("请按目录层级逐级进入，系统会在 114/116 分开前停在共同文件夹。")
        selected_folder = choose_dataset_folder(datasets, "workbench_folder")
        scoped_datasets = filter_datasets_by_folder(datasets, selected_folder)
        eight_channel_files = [
            item for item in scoped_datasets if item["metadata"].get("channels_count") == 8
        ]
        two_channel_files = [
            item for item in scoped_datasets if item["metadata"].get("channels_count") == 2
        ]
        other_files = [
            item for item in scoped_datasets if item["metadata"].get("channels_count") not in {2, 8}
        ]
        selected_8 = choose_dataset("8 通道文件", eight_channel_files, "workbench_file_8")
        selected_2 = choose_dataset("2 通道文件", two_channel_files, "workbench_file_2")
        selected_other = None
        if other_files:
            with st.expander("其他通道文件"):
                selected_other = choose_dataset("补充文件", other_files, "workbench_file_other")
        st.caption("已开启新文件自动发现；SFTP 文件仅在首次分析时进入临时缓存。")
        if st.button("刷新文件列表", width="stretch"):
            with st.spinner("正在刷新索引……"):
                scan_datasets(user["id"])
            st.cache_data.clear()
            st.rerun()
        file_info_placeholder = st.empty()

with screen_panel:
    screen_placeholder = st.empty()

for pending_dataset in (selected_8, selected_2, selected_other):
    if pending_dataset and pending_dataset["metadata"].get("metadata_pending"):
        try:
            with st.spinner(f"首次读取 {pending_dataset['name']} 的 MAT 元数据……"):
                hydrate_dataset_metadata(pending_dataset["id"])
        except Exception as exc:
            st.error(f"无法读取远程 MAT 文件：{exc}")
            st.stop()
        st.cache_data.clear()
        st.rerun()

is_paired = analysis_type in PAIRED_ANALYSIS_TYPES

if is_paired:
    render_file_info(file_info_placeholder, selected_8, selected_2)
    if not selected_8 or not selected_2:
        with screen_placeholder.container(border=True):
            st.error("此分析需要同时选择一个 8 通道文件和一个 2 通道文件。")
        st.stop()
    metadata_8 = selected_8["metadata"]
    metadata_2 = selected_2["metadata"]
    sample_rate_8 = float(metadata_8.get("sample_rate") or 0)
    sample_rate_2 = float(metadata_2.get("sample_rate") or 0)
    if sample_rate_8 <= 0 or not np.isclose(sample_rate_8, sample_rate_2):
        with screen_placeholder.container(border=True):
            st.error(f"两个文件采样率不一致：8CH={sample_rate_8:g} Hz，2CH={sample_rate_2:g} Hz。")
        st.stop()
    usable_samples = min(
        int(metadata_8.get("total_samples", 0)), int(metadata_2.get("total_samples", 0))
    )
    if usable_samples < int(round(sample_rate_8 / 50)) * 2:
        with screen_placeholder.container(border=True):
            st.error("两个文件的共同长度不足 2 个 50 Hz 周波。")
        st.stop()

    cycle_counts = definition["cycle_counts"]
    with screen_placeholder.container(border=True):
        st.markdown(
            '<div class="screen-label">周波选择与分析</div>',
            unsafe_allow_html=True,
        )
        control_columns = st.columns(3)
        if len(cycle_counts) == 1:
            cycle_count = cycle_counts[0]
            control_columns[0].text_input("每种状态周波数", str(cycle_count), disabled=True)
        else:
            cycle_count = control_columns[0].selectbox(
                "每种状态周波数", cycle_counts, key=f"paired_count_{analysis_type}"
            )
        paired_parameters: dict[str, Any] = {}
        if analysis_type == "paired_absolute_fft":
            paired_parameters["low_frequency"] = control_columns[1].number_input(
                "滤波下限 (Hz)", 0.0, sample_rate_8 / 2, 0.0
            )
            paired_parameters["high_frequency"] = control_columns[2].number_input(
                "滤波上限 (Hz)",
                0.001,
                sample_rate_8 / 2,
                sample_rate_8 / 2,
            )
        elif analysis_type == "paired_wpt_ratio":
            paired_parameters["bands"] = control_columns[1].selectbox(
                "小波包频带数量", [32, 64, 128], index=2
            )
        with st.spinner("正在读取完整波形并识别 50 Hz 周波……"):
            context = load_cycle_context(
                selected_8["id"],
                selected_8["modified_at"],
                selected_2["id"],
                selected_2["modified_at"],
                sample_rate_8,
                usable_samples,
            )
        starts = [int(item) for item in context["starts"]]
        if len(starts) < cycle_count * 2:
            st.error(f"仅识别到 {len(starts)} 个完整周波，无法分别选择 {cycle_count} 个。")
            st.stop()

        def format_cycle(start: int) -> str:
            return (
                f"周波 {starts.index(start) + 1:03d} · "
                f"{start / sample_rate_8:.6f}–"
                f"{(start + context['cycle_points']) / sample_rate_8:.6f} s"
            )

        selection_scope = f"{analysis_type}_{selected_8['id']}_{selected_2['id']}_{cycle_count}"
        noarc_key = f"noarc_{selection_scope}"
        arc_key = f"arc_{selection_scope}"
        picker_key = f"cycle_picker_{selection_scope}"
        if noarc_key not in st.session_state:
            st.session_state[noarc_key] = []
        if arc_key not in st.session_state:
            st.session_state[arc_key] = []
        st.session_state[noarc_key] = [
            item for item in st.session_state[noarc_key] if item in starts
        ][:cycle_count]
        st.session_state[arc_key] = [item for item in st.session_state[arc_key] if item in starts][
            :cycle_count
        ]

        def accept_cycle_picker() -> None:
            component_state = st.session_state.get(picker_key, {})
            payload = component_state.get("applied") if component_state else None
            if not isinstance(payload, dict):
                return
            normalized = normalize_cycle_selection(
                payload.get("noarc"),
                payload.get("arc"),
                starts,
                cycle_count,
            )
            if normalized is None:
                return
            st.session_state[noarc_key], st.session_state[arc_key] = normalized

        chart_key = f"cycle_click_chart_{selection_scope}"
        st.plotly_chart(
            build_cycle_selection_figure(context),
            key=chart_key,
            width="stretch",
            config={"scrollZoom": True, "displaylogo": False},
        )
        render_cycle_picker(
            chart_key,
            starts,
            context["cycle_points"],
            sample_rate_8,
            st.session_state[noarc_key],
            st.session_state[arc_key],
            cycle_count,
            key=picker_key,
            on_applied_change=accept_cycle_picker,
        )

        st.markdown("**精确列表选择（备用）**")
        select_columns = st.columns(2)
        noarc_starts = select_columns[0].multiselect(
            f"无弧周波（请选择 {cycle_count} 个）",
            starts,
            max_selections=cycle_count,
            format_func=format_cycle,
            key=noarc_key,
        )
        arc_starts = select_columns[1].multiselect(
            f"有弧周波（请选择 {cycle_count} 个）",
            starts,
            max_selections=cycle_count,
            format_func=format_cycle,
            key=arc_key,
        )
        st.caption(
            f"已选择：无弧 {len(noarc_starts)}/{cycle_count}，"
            f"有弧 {len(arc_starts)}/{cycle_count}。图上连续点选后需点击“确认并分析”。"
        )
        if set(noarc_starts) & set(arc_starts):
            st.error("同一个周波不能同时作为无弧和有弧，请重新选择。")
            st.stop()
        if len(noarc_starts) != cycle_count or len(arc_starts) != cycle_count:
            st.info("请在上方分别选满无弧和有弧周波。")
            st.stop()
        with st.spinner(f"正在生成{definition['label']}……"):
            output = compute_paired_preview(
                selected_8["id"],
                selected_8["modified_at"],
                tuple(metadata_8.get("channels", [])),
                selected_2["id"],
                selected_2["modified_at"],
                tuple(metadata_2.get("channels", [])),
                sample_rate_8,
                tuple(noarc_starts),
                tuple(arc_starts),
                context["cycle_points"],
                analysis_type,
                json.dumps(paired_parameters, sort_keys=True),
            )
        st.divider()
        render_paired_output(output, show_table=False)
        with st.container(key="analysis_summary"):
            metric_columns = st.columns(4)
            metric_columns[0].metric("分析通道", "8 + 2")
            metric_columns[1].metric("每种状态", f"{cycle_count} 周波")
            metric_columns[2].metric("采样率", f"{sample_rate_8:g} Hz")
            metric_columns[3].metric("单周波", f"{context['cycle_points']:,} 点")

    safe_stem = f"{selected_8['id']}_{selected_2['id']}_{analysis_type}"
    job_dataset_id = selected_8["id"]
    job_parameters = {
        "paired_dataset_2_id": selected_2["id"],
        "sample_rate": sample_rate_8,
        "cycle_count": cycle_count,
        "noarc_starts": noarc_starts,
        "arc_starts": arc_starts,
        **paired_parameters,
    }
    detail = {
        "8通道文件": selected_8["relative_path"],
        "2通道文件": selected_2["relative_path"],
        "分析方法": definition["label"],
        "采样率": sample_rate_8,
        "算法参数": job_parameters,
    }
else:
    channel_options: dict[str, tuple[dict[str, Any], str]] = {}
    add_channel_options(channel_options, selected_8, "8CH", CHANNEL_LABELS_8)
    add_channel_options(channel_options, selected_2, "2CH", CHANNEL_LABELS_2)
    if selected_other and selected_other["id"] not in {
        item["id"] for item in (selected_8, selected_2) if item
    }:
        add_channel_options(channel_options, selected_other, "其他")
    if not channel_options:
        st.warning("没有可选择的通道。请先索引一个数值数据文件。")
        st.stop()

    with st.container(border=True):
        channel_key = "_".join(
            str(item["id"]) for item in (selected_8, selected_2, selected_other) if item
        )
        if IS_ARC_PAGE:
            st.markdown("#### 固定识别数据源")
            if not selected_2:
                st.error("当前文件夹中没有找到116（2通道）文件。")
                st.stop()
            ch1_option = next(
                (
                    label
                    for label, (dataset, selected_channel) in channel_options.items()
                    if dataset["id"] == selected_2["id"]
                    and selected_channel.upper() in {"CH1", "CH01"}
                ),
                None,
            )
            if ch1_option is None:
                st.error("当前116文件中没有找到CH1通道。")
                st.stop()
            selected_channel_labels = [ch1_option]
            st.markdown("**116 文件 · CH1 通道 · 全部数据**")
            st.caption("114文件不参与识别；无需手动选择通道或周波。")
        else:
            st.markdown("#### 通道选择")
            st.markdown(
                '<div class="channel-caption">默认按照原设备的 8 通道 + 2 通道顺序排列</div>',
                unsafe_allow_html=True,
            )
        if analysis_type == "fft":
            selected_channel_labels = st.pills(
                "通道",
                list(channel_options),
                default=[list(channel_options)[0]],
                selection_mode="multi",
                label_visibility="collapsed",
                key=f"workbench_channel_fft_{channel_key}",
            ) or [list(channel_options)[0]]
            st.caption("可同时选择多个通道；所有通道共用同一组所选周波并叠加显示。")
        elif not IS_ARC_PAGE:
            selected_channel_labels = [
                st.pills(
                    "通道",
                    list(channel_options),
                    default=list(channel_options)[0],
                    selection_mode="single",
                    label_visibility="collapsed",
                    key=f"workbench_channel_{channel_key}",
                )
                or list(channel_options)[0]
            ]

    channel_selections = [
        (label, *channel_options[label]) for label in selected_channel_labels
    ]
    selected_channel_label = " + ".join(selected_channel_labels)
    _primary_label, selected_dataset, channel = channel_selections[0]
    metadata = selected_dataset["metadata"]
    total_samples = min(
        channel_length(dataset, selected_channel)
        for _label, dataset, selected_channel in channel_selections
    )
    detected_rates = [
        float(rate)
        for _label, dataset, _channel in channel_selections
        if (rate := dataset["metadata"].get("sample_rate"))
    ]
    if detected_rates and any(
        not np.isclose(rate, detected_rates[0]) for rate in detected_rates[1:]
    ):
        st.error("所选通道的采样率不一致，无法共用同一组周波。")
        st.stop()
    detected_rate = detected_rates[0] if detected_rates else None
    analysis_channel_scope = "_".join(
        f"{dataset['id']}-{selected_channel}"
        for _label, dataset, selected_channel in channel_selections
    ).replace("/", "_")
    if total_samples < 2:
        st.error("所选通道没有足够的采样点。")
        st.stop()

    fft_cycle_count = FFT_CYCLE_OPTIONS[-1]
    if analysis_type in CYCLE_SELECTION_TYPES:
        with st.container(border=True):
            st.markdown("#### 周波数量")
            fft_cycle_count = int(
                st.pills(
                    "选择用于 FFT 计算的周波数量",
                    FFT_CYCLE_OPTIONS,
                    default=FFT_CYCLE_OPTIONS[-1],
                    selection_mode="single",
                    key=f"cycle_count_{analysis_type}_{analysis_channel_scope}",
                )
                or FFT_CYCLE_OPTIONS[-1]
            )
    with st.expander("分析区间与算法参数", expanded=False):
        range_columns = st.columns(3)
        default_length = (
            total_samples
            if analysis_type in {"waveform", "arc_features", *CYCLE_SELECTION_TYPES}
            else min(
                total_samples,
                settings.max_analysis_samples,
                int(detected_rate or min(total_samples, 100_000)),
            )
        )
        start = int(
            range_columns[0].number_input(
                "起始采样点",
                0,
                total_samples - 1,
                0,
                key=f"workbench_start_{analysis_type}_{analysis_channel_scope}",
                disabled=analysis_type == "arc_features",
            )
        )
        end = int(
            range_columns[1].number_input(
                "结束采样点（不包含）",
                start + 1,
                total_samples,
                max(start + 1, min(total_samples, start + default_length)),
                key=f"workbench_end_{analysis_type}_{analysis_channel_scope}",
                disabled=analysis_type == "arc_features",
            )
        )
        sample_rate = float(
            range_columns[2].number_input(
                "采样率 (Hz)",
                min_value=0.001,
                value=float(detected_rate or 1_000_000.0),
                format="%.3f",
                key=f"workbench_rate_{analysis_channel_scope}",
            )
        )
        parameters: dict[str, Any] = {}
        if analysis_type in {"fft", "power_spectrum"}:
            frequency_columns = st.columns(3)
            parameters["min_frequency"] = frequency_columns[0].number_input(
                "最小频率 (Hz)", 0.0, sample_rate / 2, 0.0, key=f"min_freq_{analysis_type}"
            )
            parameters["max_frequency"] = frequency_columns[1].number_input(
                "最大频率 (Hz)",
                0.001,
                sample_rate / 2,
                sample_rate / 2,
                key=f"max_freq_{analysis_type}",
            )
            if analysis_type == "fft":
                parameters["detrend"] = frequency_columns[2].checkbox(
                    "去除直流分量", value=True, key="fft_detrend"
                )
            else:
                parameters["segment_length"] = frequency_columns[2].selectbox(
                    "Welch 分段长度", [512, 1024, 2048, 4096, 8192], index=3
                )
        elif analysis_type == "bandpass":
            filter_columns = st.columns(3)
            parameters["low_frequency"] = filter_columns[0].number_input(
                "下限频率 (Hz)", 0.001, sample_rate / 2, min(10.0, sample_rate / 8)
            )
            parameters["high_frequency"] = filter_columns[1].number_input(
                "上限频率 (Hz)", 0.002, sample_rate / 2, sample_rate / 4
            )
            parameters["order"] = filter_columns[2].number_input("滤波器阶数", 1, 12, 4)
        elif analysis_type == "envelope":
            parameters["smooth_ms"] = st.number_input("包络平滑窗口 (ms)", 0.0, 1000.0, 1.0, 0.1)
        elif analysis_type == "wavelet_energy":
            wavelet_columns = st.columns(2)
            parameters["wavelet"] = wavelet_columns[0].selectbox(
                "小波", ["db3", "db4", "bior3.1", "sym4", "coif3"]
            )
            parameters["level"] = wavelet_columns[1].number_input("分解层数", 1, 8, 5)
        elif analysis_type == "arc_features":
            st.caption("识别范围固定为116文件CH1通道的全部采样点。")
            threshold_columns = st.columns(2)
            parameters["probability_threshold"] = float(
                threshold_columns[0].number_input(
                    "单个半波的有弧概率阈值",
                    min_value=0.0,
                    max_value=1.0,
                    value=0.5,
                    step=0.05,
                )
            )
            parameters["required_arc_halfwaves"] = int(
                threshold_columns[1].number_input(
                    "文件夹判为有弧所需半波数",
                    min_value=1,
                    value=3,
                    step=1,
                )
            )

    if analysis_type == "arc_features":
        start = 0
        end = total_samples

    range_is_too_large = (
        analysis_type not in {"waveform", "arc_features", *CYCLE_SELECTION_TYPES}
        and end - start > settings.max_analysis_samples
    )
    if range_is_too_large:
        st.error(f"单次最多分析 {settings.max_analysis_samples:,} 个采样点，请缩小区间。")
        st.stop()
    selected_fft_starts: list[int] = []
    analysis_points = end - start
    analysis_duration = analysis_points / sample_rate
    with screen_placeholder.container(border=True):
        if analysis_type in CYCLE_SELECTION_TYPES:
            st.markdown(
                f'<div class="screen-label">选择 {fft_cycle_count} 个周波并进行'
                f'{definition["label"]}</div>',
                unsafe_allow_html=True,
            )
            with st.spinner("正在读取波形并识别 50 Hz 周波……"):
                fft_channel_refs = tuple(
                    (
                        dataset["id"],
                        dataset["modified_at"],
                        selected_channel,
                        label,
                    )
                    for label, dataset, selected_channel in channel_selections
                )
                context = load_fft_cycle_context(
                    fft_channel_refs,
                    sample_rate,
                    start,
                    end,
                )
            starts = [int(item) for item in context["starts"]]
            if len(starts) < fft_cycle_count:
                st.error(
                    f"所选区间仅识别到 {len(starts)} 个完整周波，"
                    f"至少需要 {fft_cycle_count} 个，请扩大分析区间。"
                )
                st.stop()

            def format_fft_cycle(cycle_start: int) -> str:
                return (
                    f"周波 {starts.index(cycle_start) + 1:03d} · "
                    f"{cycle_start / sample_rate:.6f}–"
                    f"{(cycle_start + context['cycle_points']) / sample_rate:.6f} s"
                )

            scope_source = (
                f"{analysis_channel_scope}|{start}|{end}|{sample_rate:g}|{fft_cycle_count}"
            )
            selection_scope = (
                f"{analysis_type}_{hashlib.sha1(scope_source.encode()).hexdigest()[:16]}"
            )
            selection_key = f"fft_cycles_{selection_scope}"
            picker_key = f"fft_cycle_picker_{selection_scope}"
            if selection_key not in st.session_state:
                st.session_state[selection_key] = []
            st.session_state[selection_key] = [
                item for item in st.session_state[selection_key] if item in starts
            ][:fft_cycle_count]

            def accept_fft_cycle_picker() -> None:
                component_state = st.session_state.get(picker_key, {})
                payload = component_state.get("applied") if component_state else None
                if not isinstance(payload, dict):
                    return
                normalized = normalize_cycle_selection(
                    payload.get("noarc"),
                    payload.get("arc"),
                    starts,
                    fft_cycle_count,
                )
                if normalized is not None:
                    combined = list(dict.fromkeys([*normalized[0], *normalized[1]]))
                    st.session_state[selection_key] = combined[:fft_cycle_count]

            chart_key = f"fft_cycle_chart_{selection_scope}"
            st.plotly_chart(
                build_fft_cycle_selection_figure(context, fft_cycle_count),
                key=chart_key,
                width="stretch",
                config={"scrollZoom": True, "displaylogo": False},
            )
            render_cycle_picker(
                chart_key,
                starts,
                context["cycle_points"],
                sample_rate,
                st.session_state[selection_key],
                [],
                fft_cycle_count,
                key=picker_key,
                on_applied_change=accept_fft_cycle_picker,
                single_mode=True,
                axis_count=1,
            )
            st.caption(
                "点击“选择”后在图中点选周波；需要撤销时点击“取消”后再点对应周波。"
                "选满后点击“确认并分析”。"
            )
            selected_fft_starts = st.multiselect(
                f"精确列表选择（请选择 {fft_cycle_count} 个）",
                starts,
                max_selections=fft_cycle_count,
                format_func=format_fft_cycle,
                key=selection_key,
            )
            st.caption(
                f"已选择 {len(selected_fft_starts)}/{fft_cycle_count} 个周波。"
                "图上连续点选后需点击“确认并分析”。"
            )
            if len(selected_fft_starts) != fft_cycle_count:
                st.info(f"请从波形上或精确列表中选满 {fft_cycle_count} 个周波。")
                st.stop()
            try:
                with st.spinner(f"正在处理 {fft_cycle_count} 个周波……"):
                    if analysis_type == "fft":
                        output = compute_fft_cycle_preview(
                            fft_channel_refs,
                            sample_rate,
                            tuple(selected_fft_starts),
                            context["cycle_points"],
                            json.dumps(parameters, ensure_ascii=False, sort_keys=True),
                        )
                    else:
                        output = compute_arc_feature_preview(
                            selected_dataset["id"],
                            selected_dataset["modified_at"],
                            channel,
                            sample_rate,
                            tuple(selected_fft_starts),
                            context["cycle_points"],
                        )
            except Exception as exc:
                st.error(f"无法生成{definition['label']}：{exc}")
                st.stop()
            analysis_points = fft_cycle_count * context["cycle_points"]
            analysis_duration = analysis_points / sample_rate
            st.divider()
        else:
            try:
                with st.spinner(f"正在生成{definition['label']}……"):
                    output = compute_preview(
                        selected_dataset["id"],
                        selected_dataset["modified_at"],
                        channel,
                        start,
                        end,
                        sample_rate,
                        analysis_type,
                        json.dumps(parameters, ensure_ascii=False, sort_keys=True),
                    )
            except Exception as exc:
                st.error(f"无法生成分析图：{exc}")
                st.stop()

        st.markdown('<div class="screen-label">分析结果</div>', unsafe_allow_html=True)
        render_analysis_output(output, show_table=False)
        with st.container(key="analysis_summary"):
            metric_columns = st.columns(4)
            metric_columns[0].metric(
                "当前通道",
                (
                    f"{len(selected_channel_labels)} 个通道"
                    if analysis_type == "fft"
                    else selected_channel_label.split(" · ")[-1]
                ),
            )
            metric_columns[1].metric(
                "分析范围",
                f"{fft_cycle_count} 周波"
                if analysis_type in CYCLE_SELECTION_TYPES
                else f"{analysis_points:,} 点",
            )
            metric_columns[2].metric("采样率", f"{sample_rate:g} Hz")
            metric_columns[3].metric("分析时长", f"{analysis_duration:.6g} s")
    with file_info_placeholder.container():
        st.divider()
        st.caption("当前数据")
        st.markdown(
            f'<div class="file-info-name">{html.escape(selected_dataset["name"])}</div>',
            unsafe_allow_html=True,
        )
        st.caption(f"{metadata.get('channels_count', '?')} 通道 · {total_samples:,} 点")
        st.caption(f"当前：{selected_channel_label}")

    safe_stem = f"{analysis_channel_scope}_{analysis_type}".replace("/", "_")
    job_dataset_id = selected_dataset["id"]
    job_parameters = {
        "channel": channel,
        "channel_label": selected_channel_label,
        "start": start,
        "end": end,
        "sample_rate": sample_rate,
        **parameters,
    }
    if analysis_type in CYCLE_SELECTION_TYPES:
        job_parameters.update(
            {
                "channels": [
                    {
                        "dataset_id": dataset["id"],
                        "channel": selected_channel,
                        "label": label,
                    }
                    for label, dataset, selected_channel in channel_selections
                ],
                "cycle_count": fft_cycle_count,
                "cycle_starts": selected_fft_starts,
                "cycle_points": context["cycle_points"],
            }
        )
    detail = {
        "文件": selected_dataset["relative_path"],
        "通道": selected_channel_labels,
        "分析方法": definition["label"],
        "采样区间": [start, end],
        "选中周波": selected_fft_starts if analysis_type in CYCLE_SELECTION_TYPES else None,
        "采样率": sample_rate,
        "算法参数": parameters,
    }

png_bytes = render_figure_bytes(output, "png")
csv_bytes = output.table.to_csv(index=False).encode("utf-8-sig")
with action_placeholder.container():
    action_columns = st.columns(3)
    save_clicked = action_columns[0].button("保存分析结果", type="primary", width="stretch")
    action_columns[1].download_button(
        "保存图片 PNG", png_bytes, f"{safe_stem}.png", "image/png", width="stretch"
    )
    action_columns[2].download_button(
        "导出数据 CSV", csv_bytes, f"{safe_stem}.csv", "text/csv", width="stretch"
    )

if save_clicked:
    job_id = create_job(user["id"], job_dataset_id, analysis_type, job_parameters)
    try:
        mark_running(job_id)
        save_job_result(job_id, user["id"], output)
        st.success(f"分析结果已保存，任务编号：{job_id[:10]}")
    except Exception as exc:
        mark_failed(job_id, exc)
        st.error(f"保存失败：{exc}")

with st.expander("查看分析指标与完整参数"):
    detail_columns = st.columns([3, 2])
    detail_columns[0].dataframe(output.table, width="stretch", hide_index=True)
    detail_columns[1].json(detail)
