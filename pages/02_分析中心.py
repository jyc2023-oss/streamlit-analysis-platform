from __future__ import annotations

import streamlit as st

from src.analysis import ANALYSIS_TYPES, run_analysis
from src.auth.ui import render_sidebar, require_user
from src.components.plots import render_analysis_output
from src.config import get_settings
from src.db import init_db
from src.services.datasets import list_datasets, load_channel
from src.services.jobs import (
    create_job,
    mark_failed,
    mark_running,
    read_artifact,
    save_job_result,
)

st.set_page_config(page_title="分析中心", page_icon="📈", layout="wide")
init_db()
user = require_user()
render_sidebar(user)
settings = get_settings()

st.title("分析中心")
st.caption("选择服务器数据和受控算法参数。每次运行都会记录算法版本并生成独立结果目录。")

datasets = list_datasets(status="ready")
if not datasets:
    st.info("没有可分析的数据。请先到“数据浏览”页面刷新索引。")
    st.stop()

dataset_labels = {f"#{item['id']} · {item['relative_path']}": item for item in datasets}
selected_dataset = dataset_labels[st.selectbox("数据文件", list(dataset_labels))]
metadata = selected_dataset["metadata"]
channels = metadata.get("channels", [])
total_samples = int(metadata.get("total_samples", 0))
if not channels or total_samples < 2:
    st.error("数据中没有可分析的数值通道。")
    st.stop()

analysis_labels = {item["label"]: key for key, item in ANALYSIS_TYPES.items()}
with st.form("analysis"):
    row = st.columns(2)
    channel = row[0].selectbox("通道", channels)
    analysis_label = row[1].selectbox("分析类型", list(analysis_labels))
    analysis_type = analysis_labels[analysis_label]

    range_columns = st.columns(3)
    start = int(range_columns[0].number_input("起始采样点", 0, total_samples - 1, 0))
    default_length = min(
        total_samples, settings.max_analysis_samples, int(metadata.get("sample_rate") or 100000)
    )
    end = int(
        range_columns[1].number_input(
            "结束采样点（不包含）",
            min_value=start + 1,
            max_value=total_samples,
            value=max(start + 1, min(total_samples, start + default_length)),
        )
    )
    detected_rate = metadata.get("sample_rate")
    sample_rate = float(
        range_columns[2].number_input(
            "采样率 (Hz)",
            min_value=0.001,
            value=float(detected_rate or 1000000.0),
            format="%.3f",
            help="BIN 读取文件头；MAT 未提供时需要人工确认。",
        )
    )

    parameters: dict = {}
    if analysis_type == "fft":
        fft_columns = st.columns(3)
        parameters["min_frequency"] = fft_columns[0].number_input(
            "最小频率 (Hz)", 0.0, sample_rate / 2, 0.0
        )
        parameters["max_frequency"] = fft_columns[1].number_input(
            "最大频率 (Hz)", 0.001, sample_rate / 2, sample_rate / 2
        )
        parameters["detrend"] = fft_columns[2].checkbox("去除直流分量", value=True)
    elif analysis_type == "bandpass":
        filter_columns = st.columns(3)
        parameters["low_frequency"] = filter_columns[0].number_input(
            "下限频率 (Hz)", 0.001, sample_rate / 2, min(10.0, sample_rate / 8)
        )
        parameters["high_frequency"] = filter_columns[1].number_input(
            "上限频率 (Hz)", 0.002, sample_rate / 2, sample_rate / 4
        )
        parameters["order"] = filter_columns[2].number_input("滤波器阶数", 1, 12, 4)
    elif analysis_type == "wavelet_energy":
        wavelet_columns = st.columns(2)
        parameters["wavelet"] = wavelet_columns[0].selectbox(
            "小波", ["db3", "db4", "bior3.1", "sym4", "coif3"]
        )
        parameters["level"] = wavelet_columns[1].number_input("分解层数", 1, 8, 5)

    submitted = st.form_submit_button("执行分析", type="primary", use_container_width=True)

if submitted:
    if end - start > settings.max_analysis_samples:
        st.error(f"单次最多分析 {settings.max_analysis_samples:,} 个采样点，请缩小区间。")
        st.stop()
    job_parameters = {
        "channel": channel,
        "start": start,
        "end": end,
        "sample_rate": sample_rate,
        **parameters,
    }
    job_id = create_job(user["id"], selected_dataset["id"], analysis_type, job_parameters)
    try:
        mark_running(job_id)
        with st.status("正在运行分析……", expanded=True) as status:
            st.write("读取服务器数据")
            values, _ = load_channel(selected_dataset["id"], channel, start, end)
            st.write(f"执行 {analysis_label}（{len(values):,} 个采样点）")
            output = run_analysis(analysis_type, values, sample_rate, parameters)
            st.write("生成 PNG、PDF、CSV 和任务清单")
            artifacts = save_job_result(job_id, user["id"], output)
            status.update(label="分析完成", state="complete", expanded=False)
        st.success(f"任务 {job_id[:10]} 已完成。")
        render_analysis_output(output)
        st.subheader("下载结果")
        download_columns = st.columns(
            len([item for item in artifacts if item["name"] != "manifest.json"])
        )
        visible_artifacts = [item for item in artifacts if item["name"] != "manifest.json"]
        for column, artifact in zip(download_columns, visible_artifacts, strict=True):
            column.download_button(
                artifact["name"],
                data=read_artifact(artifact),
                file_name=f"{job_id[:10]}_{artifact['name']}",
                mime=artifact["media_type"],
                use_container_width=True,
            )
    except Exception as exc:
        mark_failed(job_id, exc)
        st.error(f"分析失败：{exc}")
