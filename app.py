from __future__ import annotations

import streamlit as st

from src.auth.ui import current_user, render_account_bar, render_login
from src.config import get_settings
from src.db import init_db
from src.ui import render_global_theme

settings = get_settings()
st.set_page_config(page_title=settings.app_name, page_icon=":material/monitoring:", layout="wide")
render_global_theme()
init_db()

user = current_user()
if user is None:
    st.markdown('<div class="login-page-marker"></div>', unsafe_allow_html=True)
    render_login()
    st.stop()

pages = [
    st.Page("pages/01_数据浏览.py", title="数据浏览", icon=":material/folder_open:"),
    st.Page(
        "pages/02_分析中心.py",
        title="分析中心",
        icon=":material/monitoring:",
        default=True,
    ),
    st.Page("pages/03_历史任务.py", title="历史任务", icon=":material/history:"),
]
if user["role"] == "admin":
    pages.append(
        st.Page("pages/04_系统管理.py", title="系统管理", icon=":material/settings:")
    )

navigation = st.navigation(pages, position="top")
render_account_bar(user)
navigation.run()
