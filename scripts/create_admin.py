from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.auth.service import create_user
from src.db import init_db


def main() -> None:
    parser = argparse.ArgumentParser(description="创建平台管理员")
    parser.add_argument("username", nargs="?", default="admin")
    args = parser.parse_args()
    password = getpass.getpass("管理员密码（至少 10 位）：")
    confirm = getpass.getpass("再次输入密码：")
    if password != confirm:
        raise SystemExit("两次密码不一致。")
    init_db()
    user = create_user(args.username, password, "admin")
    print(f"已创建管理员：{user['username']}")


if __name__ == "__main__":
    main()
