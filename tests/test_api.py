from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.app import app
from src.auth.service import create_user
from src.config import get_settings
from src.db import init_db


def configure_api_database(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("DATA_ROOTS", str(tmp_path / "data"))
    get_settings.cache_clear()
    init_db()


def test_api_login_session_and_logout(monkeypatch, tmp_path) -> None:
    configure_api_database(monkeypatch, tmp_path)
    create_user("api-admin", "a-secure-password", "admin")

    with TestClient(app) as client:
        login = client.post(
            "/analysis-api/auth/login",
            json={"username": "api-admin", "password": "a-secure-password"},
        )
        assert login.status_code == 200
        assert login.json()["user"]["role"] == "admin"
        assert "analysis_session" in login.cookies

        profile = client.get("/analysis-api/auth/me")
        assert profile.status_code == 200
        assert profile.json()["user"]["username"] == "api-admin"

        logout = client.post("/analysis-api/auth/logout")
        assert logout.status_code == 200
        assert client.get("/analysis-api/auth/me").status_code == 401
    get_settings.cache_clear()


def test_api_protects_dataset_catalog(monkeypatch, tmp_path) -> None:
    configure_api_database(monkeypatch, tmp_path)
    with TestClient(app) as client:
        assert client.get("/analysis-api/health").status_code == 200
        response = client.get("/analysis-api/datasets")
        assert response.status_code == 401
        assert response.json()["message"] == "登录状态已失效。"
    get_settings.cache_clear()
