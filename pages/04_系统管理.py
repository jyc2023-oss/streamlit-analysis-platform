from __future__ import annotations

import shutil

import pandas as pd
import streamlit as st

from src.auth.service import create_user, list_users, set_user_active
from src.auth.ui import render_sidebar, require_user
from src.config import get_settings
from src.db import init_db, transaction
from src.services.datasets import dataset_counts, scan_datasets
from src.services.jobs import job_counts

st.set_page_config(page_title="系统管理", page_icon="⚙️", layout="wide")
init_db()
user = require_user("admin")
render_sidebar(user)
settings = get_settings()

st.title("系统管理")

st.subheader("运行状态")
usage = shutil.disk_usage(settings.app_data_dir)
datasets = dataset_counts()
jobs = job_counts()
metrics = st.columns(4)
metrics[0].metric("数据文件", datasets["total"])
metrics[1].metric("分析任务", jobs["total"])
metrics[2].metric("结果目录", str(settings.result_dir))
metrics[3].metric("磁盘可用", f"{usage.free / 1024**3:.1f} GB")

st.subheader("数据目录")
for root in settings.data_roots:
    st.write(f"{'✅' if root.exists() else '⚠️'} `{root}`")
if st.button("立即刷新全部数据索引"):
    with st.spinner("扫描中……"):
        result = scan_datasets(user["id"])
    st.success(f"扫描完成：{result}")

st.subheader("用户管理")
users = list_users()
st.dataframe(
    pd.DataFrame(
        [
            {
                "ID": item["id"],
                "用户名": item["username"],
                "角色": item["role"],
                "状态": "启用" if item["is_active"] else "禁用",
                "创建时间": item["created_at"],
            }
            for item in users
        ]
    ),
    use_container_width=True,
    hide_index=True,
)

with st.expander("创建用户"):
    with st.form("create_user"):
        username = st.text_input("用户名")
        password = st.text_input("初始密码（至少 10 位）", type="password")
        role = st.selectbox("角色", ["analyst", "admin"])
        submitted = st.form_submit_button("创建")
    if submitted:
        try:
            create_user(username, password, role)
            st.success("用户已创建。")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

with st.expander("启用或禁用用户"):
    user_labels = {f"#{item['id']} · {item['username']}": item for item in users}
    selected = user_labels[st.selectbox("用户", list(user_labels))]
    desired = st.selectbox("设置状态", ["启用", "禁用"])
    if st.button("更新用户状态"):
        try:
            set_user_active(selected["id"], desired == "启用", user["id"])
            st.success("用户状态已更新。")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

st.subheader("最近审计日志")
with transaction() as connection:
    logs = connection.execute(
        """SELECT logs.created_at, users.username, logs.action, logs.target_type,
                  logs.target_id, logs.detail_json
           FROM audit_logs AS logs
           LEFT JOIN users ON users.id = logs.user_id
           ORDER BY logs.id DESC LIMIT 100"""
    ).fetchall()
st.dataframe(pd.DataFrame([dict(row) for row in logs]), use_container_width=True, hide_index=True)
