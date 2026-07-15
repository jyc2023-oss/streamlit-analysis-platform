from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.auth.ui import require_user
from src.config import get_settings
from src.db import init_db
from src.services.datasets import (
    downsample,
    get_dataset,
    list_datasets,
    load_channel,
    scan_datasets,
)

init_db()
user = require_user()
settings = get_settings()

st.title("数据浏览")
st.caption("平台只扫描配置的数据根目录，原始文件以只读方式使用。")

with st.expander("数据源状态", expanded=False):
    for root in settings.data_roots:
        st.write(f"{'✅' if root.exists() else '⚠️'} `{root}`")

toolbar = st.columns([3, 1, 1])
search = toolbar[0].text_input("搜索文件名或相对路径", placeholder="输入关键字")
status = toolbar[1].selectbox("状态", ["全部", "ready", "pending", "error"])
if toolbar[2].button("刷新数据索引", type="primary", width="stretch"):
    with st.spinner("正在扫描数据目录并读取元信息……"):
        result = scan_datasets(user["id"])
    st.success(
        f"扫描 {result['seen']} 个文件，可用 {result['ready']} 个，失败 {result['failed']} 个。"
    )
    st.rerun()

datasets = list_datasets(search, None if status == "全部" else status)
if not datasets:
    st.info("暂无数据。请确认 DATA_ROOTS 配置并刷新索引。")
    st.stop()

table = pd.DataFrame(
    [
        {
            "ID": item["id"],
            "文件名": item["name"],
            "相对路径": item["relative_path"],
            "格式": item["extension"],
            "大小 (MB)": round(item["size_bytes"] / 1024 / 1024, 2),
            "状态": item["status"],
            "修改时间": item["modified_at"],
        }
        for item in datasets
    ]
)
st.dataframe(table, width="stretch", hide_index=True)

ready = [item for item in datasets if item["status"] == "ready"]
if not ready:
    st.warning("当前筛选结果中没有可预览的数据。")
    st.stop()

labels = {f"#{item['id']} · {item['relative_path']}": item["id"] for item in ready}
selected_label = st.selectbox("选择要预览的数据", list(labels))
dataset = get_dataset(labels[selected_label])
metadata = dataset["metadata"]

info_columns = st.columns(4)
info_columns[0].metric("通道数", metadata.get("channels_count", "未知"))
info_columns[1].metric("采样点数", metadata.get("total_samples", "未知"))
info_columns[2].metric("采样率", metadata.get("sample_rate") or "MAT 中未提供")
info_columns[3].metric("格式", metadata.get("format", dataset["extension"]))

if dataset["error_message"]:
    st.error(dataset["error_message"])

channels = metadata.get("channels", [])
total_samples = int(metadata.get("total_samples", 0))
if not channels or total_samples < 2:
    st.warning("此数据缺少可预览的通道或采样点。")
    st.stop()

with st.form("preview"):
    form_columns = st.columns(3)
    channel = form_columns[0].selectbox("通道", channels)
    start = int(
        form_columns[1].number_input(
            "起始采样点", min_value=0, max_value=total_samples - 1, value=0
        )
    )
    default_end = min(total_samples, max(2, int(metadata.get("sample_rate") or 100000)))
    end = int(
        form_columns[2].number_input(
            "结束采样点（不包含）",
            min_value=start + 1,
            max_value=total_samples,
            value=max(start + 1, default_end),
        )
    )
    preview = st.form_submit_button("生成预览", type="primary")

if preview:
    with st.spinner("正在读取并下采样……"):
        values, sample_rate = load_channel(dataset["id"], channel, start, end)
        indices, sampled = downsample(values, settings.max_preview_points)
    absolute_indices = indices + start
    x = absolute_indices / sample_rate if sample_rate else absolute_indices
    figure = go.Figure(
        go.Scattergl(x=x, y=sampled, mode="lines", line={"width": 1, "color": "#2563eb"})
    )
    figure.update_layout(
        title=f"{dataset['name']} · {channel}",
        xaxis_title="时间 (s)" if sample_rate else "采样点",
        yaxis_title="幅值",
        height=520,
        hovermode="x unified",
    )
    st.plotly_chart(figure, width="stretch")
    st.caption(f"原区间 {len(values):,} 点，预览显示 {len(sampled):,} 点。原始数据未发送到浏览器。")
