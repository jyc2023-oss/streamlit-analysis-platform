import struct

import numpy as np
from scipy.io import savemat

from src.parsers.bin_parser import bin_metadata, parse_bin_header, read_bin_channel
from src.parsers.mat_parser import mat_metadata, read_mat_channel


def test_bin_parser(tmp_path) -> None:
    path = tmp_path / "example.bin"
    data = np.arange(20, dtype="<f8").reshape(10, 2)
    header = b"TEST".ljust(32, b"\0") + struct.pack("<QIII", 123, 2, 1000, 10) + b"\0" * 4
    path.write_bytes(header + data.tobytes())
    metadata = bin_metadata(path)
    values, sample_rate = read_bin_channel(path, "CH02", 2, 5)
    assert metadata["channels_count"] == 2
    assert metadata["total_samples"] == 10
    assert sample_rate == 1000
    np.testing.assert_array_equal(values, data[2:5, 1])


def test_bin_header_can_be_parsed_without_local_data_file() -> None:
    header = b"REMOTE".ljust(32, b"\0") + struct.pack("<QIII", 123, 8, 2_000_000, 100)
    header += b"\0" * 4
    metadata = parse_bin_header(header, 56 + 100 * 8 * 8)
    assert metadata["device_name"] == "REMOTE"
    assert metadata["channels_count"] == 8
    assert metadata["sample_rate"] == 2_000_000
    assert metadata["total_samples"] == 100


def test_mat_parser(tmp_path) -> None:
    path = tmp_path / "example.mat"
    savemat(path, {"CH01": np.arange(10), "label": "ignored"})
    metadata = mat_metadata(path)
    values, sample_rate = read_mat_channel(path, "CH01", 3, 7)
    assert "CH01" in metadata["channels"]
    assert sample_rate is None
    np.testing.assert_array_equal(values, np.arange(3, 7))
