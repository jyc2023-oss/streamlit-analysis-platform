from __future__ import annotations

import streamlit as st

from src.auth.ui import current_user, render_account_bar, render_login
from src.config import get_settings
from src.db import init_db

settings = get_settings()
st.set_page_config(page_title=settings.app_name, page_icon="📊", layout="wide")
init_db()

user = current_user()
if user is None:
    left, center, right = st.columns([1, 1.3, 1])
    with center:
        render_login()
    st.stop()

pages = [
    st.Page("pages/01_数据浏览.py", title="数据浏览", icon="🗂️"),
    st.Page("pages/02_分析中心.py", title="分析中心", icon="📊", default=True),
    st.Page("pages/03_历史任务.py", title="历史任务", icon="🕘"),
]
if user["role"] == "admin":
    pages.append(st.Page("pages/04_系统管理.py", title="系统管理", icon="⚙️"))

navigation = st.navigation(pages, position="top")
render_account_bar(user)
navigation.run()
