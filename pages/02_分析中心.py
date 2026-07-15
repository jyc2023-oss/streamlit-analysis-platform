from __future__ import annotations

import json
import math
from typing import Any

import streamlit as st

from src.analysis import ANALYSIS_TYPES, run_analysis
from src.auth.ui import render_sidebar, require_user
from src.components.plots import render_analysis_output
from src.config import get_settings
from src.db import init_db
from src.services.datasets import list_datasets, load_channel, scan_datasets
from src.services.jobs import (
    create_job,
    mark_failed,
    mark_running,
    render_figure_bytes,
    save_job_result,
)

CHANNEL_LABELS_8 = ["5m", "10m", "20m", "40m", "80m", "120m", "160m", "背景支路"]
CHANNEL_LABELS_2 = ["电弧发生处", "2m主干"]


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
    del modified_at  # 文件变化时用于自动使缓存失效。
    values, _ = load_channel(dataset_id, channel, start, end)
    return run_analysis(analysis_type, values, sample_rate, json.loads(parameters_json))


def choose_dataset(title: str, datasets: list[dict[str, Any]], key: str) -> dict | None:
    if not datasets:
        st.selectbox(title, ["未找到匹配文件"], disabled=True, key=f"{key}_empty")
        return None
    labels = {f"{item['name']}  ·  #{item['id']}": item for item in datasets}
    selected = st.selectbox(title, list(labels), key=key)
    return labels[selected]


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
    channels = dataset["metadata"].get("channels", [])
    for index, channel in enumerate(channels):
        business_name = (
            business_labels[index]
            if business_labels is not None and index < len(business_labels)
            else channel
        )
        label = f"{group} · {channel} · {business_name}"
        options[label] = (dataset, channel)


st.set_page_config(page_title="分析工作台", page_icon="📈", layout="wide")
init_db()
user = require_user()
render_sidebar(user)
settings = get_settings()

st.markdown(
    """
    <style>
      .block-container {max-width: 1900px; padding-top: 1.1rem; padding-bottom: 2rem;}
      div[data-testid="stVerticalBlockBorderWrapper"] {
        border-color: #dbe4f0; border-radius: 14px; box-shadow: 0 8px 24px rgba(15,23,42,.05);
      }
      div[data-testid="stMetric"] {
        background: #f8fafc; border: 1px solid #e2e8f0; padding: .55rem .75rem; border-radius: 10px;
      }
      .screen-label {
        color:#64748b; font-size:.82rem; letter-spacing:.08em; text-transform:uppercase;
      }
      .channel-caption {color:#64748b; font-size:.88rem; margin-top:-.4rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

title_column, action_column = st.columns([5, 4], vertical_alignment="center")
with title_column:
    st.title("数据分析工作台")
    st.caption("切换分析方法、文件或通道后，中央大屏会自动刷新。")
action_placeholder = action_column.empty()

datasets = list_datasets(status="ready")
if not datasets:
    st.info("没有可分析的数据。请先到“数据浏览”页面刷新索引。")
    st.stop()

left_panel, screen_panel, right_panel = st.columns([1.25, 4.9, 1.55], gap="medium")

with left_panel:
    with st.container(border=True):
        st.markdown("#### 分析方法")
        analysis_type = st.radio(
            "选择分析方法",
            list(ANALYSIS_TYPES),
            format_func=lambda key: (
                f"{ANALYSIS_TYPES[key]['icon']}  {ANALYSIS_TYPES[key]['label']}"
            ),
            label_visibility="collapsed",
            key="workbench_analysis_type",
        )
        definition = ANALYSIS_TYPES[analysis_type]
        st.caption(definition["description"])
        st.divider()
        st.markdown("**操作提示**")
        st.caption("鼠标滚轮缩放，拖动选择区域；双击恢复完整视图。图表右上角也可以直接截图。")

with right_panel:
    with st.container(border=True):
        st.markdown("#### 分析文件")
        eight_channel_files = [
            item for item in datasets if item["metadata"].get("channels_count") == 8
        ]
        two_channel_files = [
            item for item in datasets if item["metadata"].get("channels_count") == 2
        ]
        other_files = [
            item for item in datasets if item["metadata"].get("channels_count") not in {2, 8}
        ]
        selected_8 = choose_dataset("8 通道文件", eight_channel_files, "workbench_file_8")
        selected_2 = choose_dataset("2 通道文件", two_channel_files, "workbench_file_2")
        selected_other = None
        if other_files:
            with st.expander("其他通道文件"):
                selected_other = choose_dataset("补充文件", other_files, "workbench_file_other")
        st.caption("文件来源于服务器数据索引，不会上传或复制原始数据。")
        if st.button("刷新文件列表", width="stretch"):
            with st.spinner("正在刷新索引……"):
                scan_datasets(user["id"])
            st.cache_data.clear()
            st.rerun()
        file_info_placeholder = st.empty()

with screen_panel:
    screen_placeholder = st.empty()

channel_options: dict[str, tuple[dict[str, Any], str]] = {}
add_channel_options(channel_options, selected_8, "8CH", CHANNEL_LABELS_8)
add_channel_options(channel_options, selected_2, "2CH", CHANNEL_LABELS_2)
if selected_other and selected_other["id"] not in {
    item["id"] for item in (selected_8, selected_2) if item
}:
    add_channel_options(channel_options, selected_other, "其他")

if not channel_options:
    st.warning("没有可选择的通道。请先索引一个 8 通道、2 通道或其他数值数据文件。")
    st.stop()

with st.container(border=True):
    st.markdown("#### 通道选择")
    st.markdown(
        '<div class="channel-caption">默认按照原设备的 8 通道 + 2 通道顺序排列</div>',
        unsafe_allow_html=True,
    )
    channel_key = "_".join(
        str(item["id"]) for item in (selected_8, selected_2, selected_other) if item
    )
    selected_channel_label = st.pills(
        "通道",
        list(channel_options),
        default=list(channel_options)[0],
        selection_mode="single",
        label_visibility="collapsed",
        key=f"workbench_channel_{channel_key}",
    )
    selected_channel_label = selected_channel_label or list(channel_options)[0]

selected_dataset, channel = channel_options[selected_channel_label]
metadata = selected_dataset["metadata"]
total_samples = channel_length(selected_dataset, channel)
detected_rate = metadata.get("sample_rate")
if total_samples < 2:
    st.error("所选通道没有足够的采样点。")
    st.stop()

with st.expander("分析区间与算法参数", expanded=False):
    range_columns = st.columns(3)
    default_length = min(
        total_samples,
        settings.max_analysis_samples,
        int(detected_rate or min(total_samples, 100_000)),
    )
    start = int(
        range_columns[0].number_input(
            "起始采样点",
            min_value=0,
            max_value=total_samples - 1,
            value=0,
            key=f"workbench_start_{selected_dataset['id']}_{channel}",
        )
    )
    end = int(
        range_columns[1].number_input(
            "结束采样点（不包含）",
            min_value=start + 1,
            max_value=total_samples,
            value=max(start + 1, min(total_samples, start + default_length)),
            key=f"workbench_end_{selected_dataset['id']}_{channel}",
        )
    )
    sample_rate = float(
        range_columns[2].number_input(
            "采样率 (Hz)",
            min_value=0.001,
            value=float(detected_rate or 1_000_000.0),
            format="%.3f",
            help="BIN 自动读取文件头；MAT 文件需要人工确认。",
            key=f"workbench_rate_{selected_dataset['id']}",
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

if end - start > settings.max_analysis_samples:
    st.error(f"单次最多分析 {settings.max_analysis_samples:,} 个采样点，请缩小区间。")
    st.stop()

parameters_json = json.dumps(parameters, ensure_ascii=False, sort_keys=True)
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
            parameters_json,
        )
except Exception as exc:
    with screen_placeholder.container(border=True):
        st.error(f"无法生成分析图：{exc}")
    st.stop()

with screen_placeholder.container(border=True):
    st.markdown('<div class="screen-label">ANALYSIS DISPLAY</div>', unsafe_allow_html=True)
    render_analysis_output(output, show_table=False)
    metric_columns = st.columns(4)
    metric_columns[0].metric("当前通道", selected_channel_label.split(" · ")[-1])
    metric_columns[1].metric("分析点数", f"{end - start:,}")
    metric_columns[2].metric("采样率", f"{sample_rate:g} Hz")
    metric_columns[3].metric("分析时长", f"{(end - start) / sample_rate:.6g} s")

with file_info_placeholder.container():
    st.divider()
    st.caption("当前数据")
    st.write(f"**{selected_dataset['name']}**")
    st.caption(f"{metadata.get('channels_count', '?')} 通道 · {total_samples:,} 点")
    st.caption(f"当前：{channel}")

safe_stem = f"{selected_dataset['id']}_{channel}_{analysis_type}".replace("/", "_")
png_bytes = render_figure_bytes(output, "png")
csv_bytes = output.table.to_csv(index=False).encode("utf-8-sig")
with action_placeholder.container():
    action_columns = st.columns(3)
    save_clicked = action_columns[0].button("保存分析结果", type="primary", width="stretch")
    action_columns[1].download_button(
        "保存图片 PNG",
        data=png_bytes,
        file_name=f"{safe_stem}.png",
        mime="image/png",
        width="stretch",
    )
    action_columns[2].download_button(
        "导出数据 CSV",
        data=csv_bytes,
        file_name=f"{safe_stem}.csv",
        mime="text/csv",
        width="stretch",
    )

if save_clicked:
    job_parameters = {
        "channel": channel,
        "channel_label": selected_channel_label,
        "start": start,
        "end": end,
        "sample_rate": sample_rate,
        **parameters,
    }
    job_id = create_job(user["id"], selected_dataset["id"], analysis_type, job_parameters)
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
    detail_columns[1].json(
        {
            "文件": selected_dataset["relative_path"],
            "通道": selected_channel_label,
            "分析方法": definition["label"],
            "采样区间": [start, end],
            "采样率": sample_rate,
            "算法参数": parameters,
        }
    )
