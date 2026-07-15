from __future__ import annotations

from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from src.db import audit, transaction, utc_now

_hasher = PasswordHasher()


def count_users() -> int:
    with transaction() as connection:
        return int(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0])


def create_user(username: str, password: str, role: str = "analyst") -> dict[str, Any]:
    username = username.strip()
    if len(username) < 3:
        raise ValueError("用户名至少需要 3 个字符。")
    if len(password) < 10:
        raise ValueError("密码至少需要 10 个字符。")
    if role not in {"admin", "analyst"}:
        raise ValueError("无效的用户角色。")
    with transaction() as connection:
        cursor = connection.execute(
            """INSERT INTO users (username, password_hash, role, is_active, created_at)
            VALUES (?, ?, ?, 1, ?)""",
            (username, _hasher.hash(password), role, utc_now()),
        )
        user_id = int(cursor.lastrowid)
        row = connection.execute(
            "SELECT id, username, role, is_active, created_at FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    audit("user.created", user_id=user_id, target_type="user", target_id=str(user_id))
    return dict(row)


def authenticate(username: str, password: str) -> dict[str, Any] | None:
    with transaction() as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE AND is_active = 1",
            (username.strip(),),
        ).fetchone()
        if row is None:
            return None
        try:
            _hasher.verify(row["password_hash"], password)
        except VerifyMismatchError:
            return None
        if _hasher.check_needs_rehash(row["password_hash"]):
            connection.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (_hasher.hash(password), row["id"]),
            )
        user = {key: row[key] for key in ("id", "username", "role", "is_active", "created_at")}
    audit("auth.login", user_id=user["id"])
    return user


def list_users() -> list[dict[str, Any]]:
    with transaction() as connection:
        rows = connection.execute(
            "SELECT id, username, role, is_active, created_at FROM users ORDER BY id"
        ).fetchall()
    return [dict(row) for row in rows]


def set_user_active(user_id: int, active: bool, actor_id: int) -> None:
    if user_id == actor_id and not active:
        raise ValueError("不能禁用当前登录账号。")
    with transaction() as connection:
        connection.execute("UPDATE users SET is_active = ? WHERE id = ?", (int(active), user_id))
    audit(
        "user.status_changed",
        user_id=actor_id,
        target_type="user",
        target_id=str(user_id),
        detail={"active": active},
    )
