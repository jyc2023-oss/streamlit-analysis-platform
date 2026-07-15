from __future__ import annotations

import streamlit as st

from src.auth.ui import current_user, render_login, render_sidebar
from src.config import get_settings
from src.db import init_db
from src.services.datasets import dataset_counts
from src.services.jobs import job_counts, list_jobs

settings = get_settings()
st.set_page_config(page_title=settings.app_name, page_icon="📊", layout="wide")
init_db()

user = current_user()
if user is None:
    left, center, right = st.columns([1, 1.3, 1])
    with center:
        render_login()
    st.stop()

render_sidebar(user)
st.title(settings.app_name)
st.caption("直接使用服务器采集数据，完成预览、分析和结果追溯。")

datasets = dataset_counts()
jobs = job_counts()
columns = st.columns(4)
columns[0].metric("已索引数据", datasets["total"])
columns[1].metric("可用数据", datasets["ready"])
columns[2].metric("成功任务", jobs["success"])
columns[3].metric("失败任务", jobs["failed"])

st.subheader("开始使用")
action_columns = st.columns(3)
with action_columns[0]:
    st.markdown("#### 1. 浏览数据")
    st.write("索引服务器目录中的 MAT/BIN 文件并预览通道波形。")
    if st.button("打开数据浏览", width="stretch"):
        st.switch_page("pages/01_数据浏览.py")
with action_columns[1]:
    st.markdown("#### 2. 执行分析")
    st.write("配置采样区间和算法参数，生成可下载的分析结果。")
    if st.button("打开分析中心", width="stretch"):
        st.switch_page("pages/02_分析中心.py")
with action_columns[2]:
    st.markdown("#### 3. 查看历史")
    st.write("查看任务参数、运行状态和已生成的结果文件。")
    if st.button("打开历史任务", width="stretch"):
        st.switch_page("pages/03_历史任务.py")

st.subheader("最近任务")
recent = list_jobs(user["id"], user["role"] == "admin", limit=10)
if not recent:
    st.info("暂无分析任务。请先索引数据并运行一次分析。")
else:
    st.dataframe(
        [
            {
                "任务 ID": item["id"][:10],
                "数据": item["dataset_name"],
                "分析类型": item["analysis_type"],
                "状态": item["status"],
                "创建时间": item["created_at"],
                "用户": item["username"],
            }
            for item in recent
        ],
        width="stretch",
        hide_index=True,
    )
