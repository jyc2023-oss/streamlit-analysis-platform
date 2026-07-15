from __future__ import annotations

from pathlib import Path

from src.config import get_settings


def ensure_allowed_data_path(path: str | Path) -> Path:
    candidate = Path(path).expanduser().resolve(strict=True)
    for root in get_settings().data_roots:
        try:
            candidate.relative_to(root.resolve())
            if not candidate.is_file():
                raise ValueError("目标不是文件。")
            return candidate
        except ValueError:
            continue
    raise PermissionError("数据路径不在允许的根目录中。")


def ensure_allowed_result_path(path: str | Path) -> Path:
    candidate = Path(path).expanduser().resolve(strict=True)
    result_root = get_settings().result_dir.resolve()
    try:
        candidate.relative_to(result_root)
    except ValueError as exc:
        raise PermissionError("结果路径不在允许的目录中。") from exc
    if not candidate.is_file():
        raise ValueError("结果文件不存在。")
    return candidate
