from __future__ import annotations

import html
from datetime import UTC, datetime, timedelta

import streamlit as st

from src.auth.service import authenticate, count_users, create_user
from src.config import get_settings
from src.db import audit


def current_user() -> dict | None:
    user = st.session_state.get("user")
    last_seen = st.session_state.get("last_seen")
    if user and last_seen:
        timeout = timedelta(minutes=get_settings().session_idle_minutes)
        if datetime.now(UTC) - last_seen > timeout:
            st.session_state.clear()
            return None
        st.session_state["last_seen"] = datetime.now(UTC)
    return user


def render_login() -> None:
    st.title(get_settings().app_name)
    st.caption("内部数据分析系统 · 请使用授权账号登录")

    if count_users() == 0:
        if get_settings().app_env == "production":
            st.error("生产环境尚未初始化管理员，请在服务器执行 scripts/create_admin.py。")
            st.stop()
        st.warning("系统尚未创建管理员。请完成一次性初始化。")
        with st.form("bootstrap_admin"):
            username = st.text_input("管理员用户名", value="admin")
            password = st.text_input("管理员密码", type="password")
            password_confirm = st.text_input("确认密码", type="password")
            submitted = st.form_submit_button("创建管理员", type="primary")
        if submitted:
            if password != password_confirm:
                st.error("两次输入的密码不一致。")
            else:
                try:
                    create_user(username, password, "admin")
                    st.success("管理员已创建，请登录。")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        return

    with st.form("login"):
        username = st.text_input("用户名")
        password = st.text_input("密码", type="password")
        submitted = st.form_submit_button("登录", type="primary", width="stretch")
    if submitted:
        user = authenticate(username, password)
        if user is None:
            st.error("用户名或密码错误。")
        else:
            st.session_state["user"] = user
            st.session_state["last_seen"] = datetime.now(UTC)
            st.rerun()


def require_user(role: str | None = None) -> dict:
    user = current_user()
    if user is None:
        st.warning("请先从首页登录。")
        if st.button("返回登录页"):
            st.switch_page("app.py")
        st.stop()
    if role == "admin" and user["role"] != "admin":
        st.error("此页面仅管理员可以访问。")
        st.stop()
    return user


def render_account_bar(user: dict) -> None:
    """Render compact account controls below the horizontal navigation."""
    st.html(
        """
        <style>
        .account-bar-label {
            color: #64748b;
            font-size: 0.85rem;
            line-height: 2.4rem;
            text-align: right;
        }
        div[data-testid="stHorizontalBlock"]:has(.account-bar-label) {
            align-items: center;
            min-height: 2.5rem;
        }
        </style>
        """
    )
    brand, identity, logout = st.columns([8, 1.2, 0.9], vertical_alignment="center")
    with brand:
        st.markdown(
            '<div class="app-wordmark">服务器数据分析平台<span>实时服务器数据</span></div>',
            unsafe_allow_html=True,
        )
    with identity:
        role = "管理员" if user["role"] == "admin" else "分析人员"
        st.markdown(
            f'<div class="account-bar-label">{html.escape(user["username"])} · {role}</div>',
            unsafe_allow_html=True,
        )
    with logout:
        if st.button("退出登录", width="stretch", key="top_logout"):
            audit("auth.logout", user_id=user["id"])
            st.session_state.clear()
            st.switch_page("app.py")
