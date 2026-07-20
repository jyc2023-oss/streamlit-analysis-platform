from __future__ import annotations

import hashlib
import json
import os
import posixpath
import stat
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote, unquote, urlsplit

import paramiko

from src.config import Settings, get_settings
from src.parsers import SUPPORTED_EXTENSIONS
from src.parsers.bin_parser import HEADER_SIZE, parse_bin_header

_CACHE_LOCKS: dict[str, threading.Lock] = {}
_CACHE_LOCKS_GUARD = threading.Lock()


@dataclass(frozen=True)
class RemoteEntry:
    uri: str
    root_uri: str
    remote_path: str
    relative_path: str
    name: str
    extension: str
    size_bytes: int
    modified_at: str
    metadata: dict[str, Any]
    error_message: str | None = None


def remote_uri(path: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    normalized = posixpath.normpath("/" + path.lstrip("/"))
    return f"sftp://{settings.sftp_host}:{settings.sftp_port}{quote(normalized, safe='/')}"


def parse_remote_uri(uri: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    parsed = urlsplit(uri)
    if parsed.scheme != "sftp" or parsed.hostname != settings.sftp_host:
        raise PermissionError("远程数据地址不属于已配置的 SFTP 数据源。")
    if (parsed.port or 22) != settings.sftp_port:
        raise PermissionError("远程数据端口与已配置的 SFTP 数据源不一致。")
    path = posixpath.normpath(unquote(parsed.path))
    root = posixpath.normpath(settings.sftp_remote_root)
    if path != root and not path.startswith(root.rstrip("/") + "/"):
        raise PermissionError("远程数据路径不在允许的 SFTP 根目录中。")
    return path


def is_remote_uri(value: str) -> bool:
    return value.startswith("sftp://")


@contextmanager
def sftp_client(settings: Settings | None = None) -> Iterator[paramiko.SFTPClient]:
    settings = settings or get_settings()
    if not settings.sftp_enabled:
        raise RuntimeError("SFTP 数据源尚未启用。")
    if not settings.sftp_host or not settings.sftp_username:
        raise RuntimeError("SFTP_HOST 和 SFTP_USERNAME 必须配置。")
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    known_hosts = Path.home() / ".ssh" / "known_hosts"
    if known_hosts.is_file():
        client.load_host_keys(str(known_hosts))
    client.set_missing_host_key_policy(
        paramiko.AutoAddPolicy()
        if settings.sftp_allow_unknown_host_key
        else paramiko.RejectPolicy()
    )
    connect_args: dict[str, Any] = {
        "hostname": settings.sftp_host,
        "port": settings.sftp_port,
        "username": settings.sftp_username,
        "timeout": 15,
        "banner_timeout": 15,
        "auth_timeout": 15,
        "look_for_keys": not bool(settings.sftp_password or settings.sftp_private_key_path),
        "allow_agent": True,
    }
    if settings.sftp_password:
        connect_args["password"] = settings.sftp_password
    if settings.sftp_private_key_path:
        connect_args["key_filename"] = str(settings.sftp_private_key_path)
        if settings.sftp_private_key_passphrase:
            connect_args["passphrase"] = settings.sftp_private_key_passphrase
    client.connect(**connect_args)
    channel = client.open_sftp()
    try:
        yield channel
    finally:
        channel.close()
        client.close()


def scan_remote_entries(
    settings: Settings | None = None,
    known_entries: dict[str, dict[str, Any]] | None = None,
) -> list[RemoteEntry]:
    settings = settings or get_settings()
    root = posixpath.normpath(settings.sftp_remote_root)
    root_uri = remote_uri(root, settings)
    entries: list[RemoteEntry] = []
    with sftp_client(settings) as client:
        pending = [root]
        while pending and len(entries) < settings.max_scan_files:
            directory = pending.pop()
            for attributes in client.listdir_attr(directory):
                path = posixpath.join(directory, attributes.filename)
                if stat.S_ISDIR(attributes.st_mode):
                    pending.append(path)
                    continue
                if not stat.S_ISREG(attributes.st_mode):
                    continue
                extension = PurePosixPath(path).suffix.lower()
                if extension not in SUPPORTED_EXTENSIONS:
                    continue
                uri = remote_uri(path, settings)
                modified_at = datetime.fromtimestamp(attributes.st_mtime, UTC).isoformat()
                known = (known_entries or {}).get(uri)
                unchanged = (
                    known is not None
                    and int(known["size_bytes"]) == int(attributes.st_size)
                    and str(known["modified_at"]) == modified_at
                )
                metadata: dict[str, Any]
                error_message: str | None = None
                if unchanged:
                    metadata = dict(known["metadata"])
                    error_message = known.get("error_message")
                elif extension == ".bin":
                    try:
                        with client.open(path, "rb") as handle:
                            header = handle.read(HEADER_SIZE)
                        metadata = parse_bin_header(header, int(attributes.st_size))
                        metadata["channels"] = [
                            f"CH{index + 1:02d}" for index in range(metadata["channels_count"])
                        ]
                        metadata["duration_seconds"] = (
                            metadata["total_samples"] / metadata["sample_rate"]
                        )
                        metadata["format"] = "bin-float64-le-v1"
                    except Exception as exc:
                        metadata = {"format": "remote-bin", "channels": [], "channels_count": 0}
                        error_message = str(exc)[:1000]
                else:
                    error_message = None
                    metadata = {
                        "format": "remote-mat-unloaded",
                        "channels": [],
                        "channels_count": 0,
                        "sample_rate": None,
                        "total_samples": 0,
                        "metadata_pending": True,
                    }
                relative = posixpath.relpath(path, root)
                entries.append(
                    RemoteEntry(
                        uri=uri,
                        root_uri=root_uri,
                        remote_path=path,
                        relative_path=relative,
                        name=attributes.filename,
                        extension=extension,
                        size_bytes=int(attributes.st_size),
                        modified_at=modified_at,
                        metadata=metadata,
                        error_message=error_message,
                    )
                )
                if len(entries) >= settings.max_scan_files:
                    break
    return entries


def _cache_paths(uri: str, extension: str, settings: Settings) -> tuple[Path, Path]:
    cache_root = settings.cache_dir / "sftp"
    cache_root.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(uri.encode("utf-8")).hexdigest()
    data_path = cache_root / f"{digest}{extension.lower()}"
    return data_path, data_path.with_suffix(data_path.suffix + ".json")


def _cache_lock(uri: str) -> threading.Lock:
    with _CACHE_LOCKS_GUARD:
        return _CACHE_LOCKS.setdefault(uri, threading.Lock())


def materialize_remote_dataset(dataset: dict[str, Any]) -> Path:
    with _cache_lock(str(dataset["path"])):
        return _materialize_remote_dataset(dataset)


def _materialize_remote_dataset(dataset: dict[str, Any]) -> Path:
    settings = get_settings()
    uri = str(dataset["path"])
    remote_path = parse_remote_uri(uri, settings)
    data_path, marker_path = _cache_paths(uri, str(dataset["extension"]), settings)
    expected = {
        "uri": uri,
        "size_bytes": int(dataset["size_bytes"]),
        "modified_at": str(dataset["modified_at"]),
    }
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        marker = None
    cache_is_valid = (
        data_path.is_file()
        and marker == expected
        and data_path.stat().st_size == expected["size_bytes"]
    )
    if cache_is_valid:
        os.utime(data_path, None)
        return data_path

    temporary = data_path.with_suffix(data_path.suffix + ".part")
    temporary.unlink(missing_ok=True)
    try:
        with sftp_client(settings) as client:
            client.get(remote_path, str(temporary))
        if temporary.stat().st_size != expected["size_bytes"]:
            raise OSError("SFTP 下载文件大小与远程索引不一致。")
        os.replace(temporary, data_path)
        marker_path.write_text(json.dumps(expected, ensure_ascii=False), encoding="utf-8")
    finally:
        temporary.unlink(missing_ok=True)
    cleanup_sftp_cache(settings, keep={data_path})
    return data_path


def cleanup_sftp_cache(
    settings: Settings | None = None, *, keep: set[Path] | None = None
) -> dict[str, int]:
    settings = settings or get_settings()
    cache_root = settings.cache_dir / "sftp"
    if not cache_root.is_dir():
        return {"removed": 0, "bytes_removed": 0}
    protected = {path.resolve() for path in (keep or set())}
    now = time.time()
    ttl_seconds = settings.sftp_cache_ttl_hours * 3600
    files = [
        path
        for path in cache_root.iterdir()
        if path.is_file() and not path.name.endswith((".json", ".part"))
    ]
    total = sum(path.stat().st_size for path in files)
    removed = bytes_removed = 0
    for path in sorted(files, key=lambda item: item.stat().st_atime):
        size = path.stat().st_size
        expired = now - path.stat().st_atime > ttl_seconds
        over_limit = total > settings.sftp_cache_max_bytes
        if path.resolve() in protected or not (expired or over_limit):
            continue
        path.unlink(missing_ok=True)
        path.with_suffix(path.suffix + ".json").unlink(missing_ok=True)
        total -= size
        removed += 1
        bytes_removed += size
    for partial in cache_root.glob("*.part"):
        if now - partial.stat().st_mtime > 3600:
            partial.unlink(missing_ok=True)
    return {"removed": removed, "bytes_removed": bytes_removed}
