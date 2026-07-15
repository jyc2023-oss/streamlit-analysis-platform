from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
from scipy.io import savemat


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

    name = b"DEMO".ljust(32, b"\0")
    header = name + struct.pack("<QIII", 0, 2, sample_rate, len(time)) + b"\0" * 4
    interleaved = np.column_stack([ch1, ch2]).astype("<f8")
    with (output / "demo_waveform.bin").open("wb") as handle:
        handle.write(header)
        handle.write(interleaved.tobytes())
    print(f"演示数据已生成：{output}")


if __name__ == "__main__":
    main()
