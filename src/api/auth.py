from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Cookie, HTTPException, Request, Response, WebSocket, status

from src.config import get_settings
from src.db import audit, transaction, utc_now

COOKIE_NAME = "analysis_session"


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_web_session(user_id: int, response: Response) -> None:
    settings = get_settings()
    token = secrets.token_urlsafe(48)
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=settings.session_idle_minutes)
    with transaction() as connection:
        connection.execute("DELETE FROM web_sessions WHERE expires_at <= ?", (now.isoformat(),))
        connection.execute(
            """INSERT INTO web_sessions
            (token_hash, user_id, created_at, last_seen, expires_at)
            VALUES (?, ?, ?, ?, ?)""",
            (_token_hash(token), user_id, now.isoformat(), now.isoformat(), expires.isoformat()),
        )
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.session_idle_minutes * 60,
        httponly=True,
        secure=settings.web_cookie_secure,
        samesite="lax",
        path="/",
    )


def delete_web_session(token: str | None, response: Response) -> None:
    if token:
        with transaction() as connection:
            connection.execute(
                "DELETE FROM web_sessions WHERE token_hash = ?", (_token_hash(token),)
            )
    response.delete_cookie(COOKIE_NAME, path="/")


def _session_user(token: str | None, *, touch: bool = True) -> dict[str, Any] | None:
    if not token:
        return None
    now = datetime.now(UTC)
    settings = get_settings()
    with transaction() as connection:
        row = connection.execute(
            """SELECT users.id, users.username, users.role, users.is_active,
            users.created_at, sessions.expires_at
            FROM web_sessions AS sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token_hash = ?""",
            (_token_hash(token),),
        ).fetchone()
        if row is None:
            return None
        if not row["is_active"] or datetime.fromisoformat(row["expires_at"]) <= now:
            connection.execute(
                "DELETE FROM web_sessions WHERE token_hash = ?", (_token_hash(token),)
            )
            return None
        if touch:
            expires = now + timedelta(minutes=settings.session_idle_minutes)
            connection.execute(
                """UPDATE web_sessions SET last_seen = ?, expires_at = ?
                WHERE token_hash = ?""",
                (now.isoformat(), expires.isoformat(), _token_hash(token)),
            )
    return {key: row[key] for key in ("id", "username", "role", "is_active", "created_at")}


def require_api_user(
    request: Request,
    analysis_session: str | None = Cookie(default=None),
) -> dict[str, Any]:
    del request
    user = _session_user(analysis_session)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "登录状态已失效。")
    return user


def require_admin(user: dict[str, Any]) -> dict[str, Any]:
    if user["role"] != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "仅管理员可以执行此操作。")
    return user


async def websocket_user(websocket: WebSocket) -> dict[str, Any] | None:
    return _session_user(websocket.cookies.get(COOKIE_NAME), touch=False)


def find_or_create_sso_user(profile: dict[str, Any]) -> dict[str, Any]:
    username = str(profile.get("username") or profile.get("userName") or "").strip()
    if len(username) < 3:
        raise ValueError("SSO 返回的用户名无效。")
    roles = profile.get("roles") or []
    role_values = {str(item).lower() for item in roles}
    role = "admin" if "admin" in role_values or "administrator" in role_values else "analyst"
    with transaction() as connection:
        row = connection.execute(
            "SELECT id, username, role, is_active, created_at FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if row is not None:
            if row["role"] != role:
                connection.execute("UPDATE users SET role = ? WHERE id = ?", (role, row["id"]))
            return {**dict(row), "role": role}

    from src.auth.service import create_user

    user = create_user(username, secrets.token_urlsafe(32), role)
    audit(
        "auth.sso_user_linked",
        user_id=user["id"],
        target_type="external_user",
        target_id=str(profile.get("userId") or profile.get("id") or username),
    )
    return user


def login_audit(user: dict[str, Any], method: str) -> None:
    audit("auth.web_login", user_id=user["id"], detail={"method": method, "at": utc_now()})
