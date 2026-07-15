from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from src.parsers.bin_parser import bin_metadata, read_bin_channel
from src.parsers.mat_parser import mat_metadata, read_mat_channel

SUPPORTED_EXTENSIONS = {".mat", ".bin"}


def read_metadata(path: Path) -> dict[str, Any]:
    extension = path.suffix.lower()
    if extension == ".mat":
        return mat_metadata(path)
    if extension == ".bin":
        return bin_metadata(path)
    raise ValueError(f"暂不支持 {extension} 格式。")


def read_channel(
    path: Path,
    channel: str,
    start: int = 0,
    end: int | None = None,
) -> tuple[np.ndarray, float | None]:
    extension = path.suffix.lower()
    if extension == ".mat":
        return read_mat_channel(path, channel, start, end)
    if extension == ".bin":
        return read_bin_channel(path, channel, start, end)
    raise ValueError(f"暂不支持 {extension} 格式。")
