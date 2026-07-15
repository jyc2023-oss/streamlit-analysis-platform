from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
from scipy.io import savemat


def write_bin(path: Path, data: np.ndarray, sample_rate: int, device_name: str) -> None:
    name = device_name.encode("utf-8").ljust(32, b"\0")[:32]
    header = name + struct.pack("<QIII", 0, data.shape[1], sample_rate, data.shape[0]) + b"\0" * 4
    with path.open("wb") as handle:
        handle.write(header)
        handle.write(np.asarray(data, dtype="<f8").tobytes())


def main() -> None:
    output = Path(__file__).resolve().parents[1] / "sample_data"
    output.mkdir(parents=True, exist_ok=True)
    sample_rate = 20_000
    duration = 1.0
    time = np.arange(int(sample_rate * duration)) / sample_rate
    ch1 = np.sin(2 * np.pi * 50 * time) + 0.25 * np.sin(2 * np.pi * 1000 * time)
    ch2 = 0.7 * np.sin(2 * np.pi * 120 * time) + 0.05 * np.random.default_rng(42).normal(
        size=time.size
    )
    savemat(output / "demo_waveform.mat", {"CH01": ch1, "CH02": ch2})

    rng = np.random.default_rng(2026)
    channels_8 = np.column_stack(
        [
            np.sin(2 * np.pi * (50 + index * 25) * time)
            + 0.12 * np.sin(2 * np.pi * (800 + index * 150) * time)
            + 0.02 * rng.normal(size=time.size)
            for index in range(8)
        ]
    )
    channels_2 = np.column_stack([ch1, ch2])
    write_bin(output / "demo_8ch.bin", channels_8, sample_rate, "DEMO-8CH")
    write_bin(output / "demo_2ch.bin", channels_2, sample_rate, "DEMO-2CH")
    print(f"演示数据已生成：{output}")


if __name__ == "__main__":
    main()
