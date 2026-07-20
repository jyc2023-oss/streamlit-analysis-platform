from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace

import pytest

from src.config import get_settings
from src.services import sftp


def remote_settings(tmp_path):
    return replace(
        get_settings(),
        cache_dir=tmp_path / "cache",
        sftp_enabled=True,
        sftp_host="data.internal",
        sftp_port=22,
        sftp_username="analyst",
        sftp_remote_root="/srv/data",
    )


def test_remote_uri_is_scoped_to_configured_root(tmp_path) -> None:
    settings = remote_settings(tmp_path)
    uri = sftp.remote_uri("/srv/data/实验 A/a.bin", settings)
    assert sftp.parse_remote_uri(uri, settings) == "/srv/data/实验 A/a.bin"
    outside = sftp.remote_uri("/srv/private/a.bin", settings)
    with pytest.raises(PermissionError):
        sftp.parse_remote_uri(outside, settings)


def test_remote_dataset_is_downloaded_once_and_reused(tmp_path, monkeypatch) -> None:
    settings = remote_settings(tmp_path)
    content = b"remote waveform"
    calls = []

    class FakeClient:
        def get(self, remote_path, local_path):
            calls.append(remote_path)
            with open(local_path, "wb") as handle:
                handle.write(content)

    @contextmanager
    def fake_client(_settings=None):
        yield FakeClient()

    monkeypatch.setattr(sftp, "get_settings", lambda: settings)
    monkeypatch.setattr(sftp, "sftp_client", fake_client)
    dataset = {
        "path": sftp.remote_uri("/srv/data/a.bin", settings),
        "extension": ".bin",
        "size_bytes": len(content),
        "modified_at": "2026-07-20T00:00:00+00:00",
    }
    first = sftp.materialize_remote_dataset(dataset)
    second = sftp.materialize_remote_dataset(dataset)
    assert first == second
    assert first.read_bytes() == content
    assert calls == ["/srv/data/a.bin"]
