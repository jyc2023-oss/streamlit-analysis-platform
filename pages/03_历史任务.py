from __future__ import annotations

import pandas as pd
import streamlit as st

from src.auth.ui import render_sidebar, require_user
from src.db import init_db
from src.services.jobs import get_artifacts, list_jobs, read_artifact

st.set_page_config(page_title="历史任务", page_icon="🕘", layout="wide")
init_db()
user = require_user()
render_sidebar(user)

st.title("历史任务")
is_admin = user["role"] == "admin"
jobs = list_jobs(user["id"], is_admin, limit=200)
if not jobs:
    st.info("暂无任务记录。")
    st.stop()

st.dataframe(
    pd.DataFrame(
        [
            {
                "任务 ID": item["id"][:10],
                "数据": item["dataset_name"],
                "算法": item["analysis_type"],
                "版本": item["algorithm_version"],
                "状态": item["status"],
                "用户": item["username"],
                "创建时间": item["created_at"],
                "完成时间": item["finished_at"],
            }
            for item in jobs
        ]
    ),
    use_container_width=True,
    hide_index=True,
)

labels = {f"{item['id'][:10]} · {item['dataset_name']} · {item['status']}": item for item in jobs}
job = labels[st.selectbox("查看任务详情", list(labels))]
detail_columns = st.columns(2)
with detail_columns[0]:
    st.markdown("**运行参数**")
    st.json(job["parameters"])
with detail_columns[1]:
    st.markdown("**任务信息**")
    st.write(f"完整 ID：`{job['id']}`")
    st.write(f"状态：`{job['status']}`")
    st.write(f"算法版本：`{job['algorithm_version']}`")
    if job["error_message"]:
        st.error(job["error_message"])

if job["status"] == "success":
    artifacts = get_artifacts(job["id"], user["id"], is_admin)
    st.subheader("结果文件")
    for artifact in artifacts:
        st.download_button(
            f"下载 {artifact['name']}（{artifact['size_bytes'] / 1024:.1f} KB）",
            data=read_artifact(artifact),
            file_name=f"{job['id'][:10]}_{artifact['name']}",
            mime=artifact["media_type"],
            key=f"artifact-{artifact['id']}",
        )
