import numpy as np

from src.services.datasets import (
    downsample,
    filter_datasets_by_folder,
    folder_choices,
)


def test_downsample_preserves_extrema() -> None:
    values = np.zeros(10_000)
    values[123] = 50
    values[4567] = -30
    _, sampled = downsample(values, 500)
    assert sampled.max() == 50
    assert sampled.min() == -30
    assert len(sampled) <= 500


def test_downsample_keeps_short_input() -> None:
    values = np.arange(10)
    indices, sampled = downsample(values, 100)
    np.testing.assert_array_equal(indices, np.arange(10))
    np.testing.assert_array_equal(sampled, values)


def test_folder_choices_stop_before_channel_folders_split() -> None:
    datasets = [
        {
            "relative_path": "2026-07-01/实验A/FTP/NET9770_114/a.bin",
            "metadata": {"channels_count": 8},
        },
        {
            "relative_path": "2026-07-01/实验A/FTP/NET9770_116/b.bin",
            "metadata": {"channels_count": 2},
        },
        {
            "relative_path": "2026-07-01/实验B/FTP/NET9770_114/c.bin",
            "metadata": {"channels_count": 8},
        },
        {
            "relative_path": "2026-07-01/实验B/FTP/NET9770_116/d.bin",
            "metadata": {"channels_count": 2},
        },
    ]
    required = {8, 2}
    assert folder_choices(datasets, (), required) == ["2026-07-01"]
    assert folder_choices(datasets, ("2026-07-01",), required) == ["实验A", "实验B"]
    assert folder_choices(datasets, ("2026-07-01", "实验A"), required) == ["FTP"]
    assert folder_choices(datasets, ("2026-07-01", "实验A", "FTP"), required) == []

    scoped = filter_datasets_by_folder(datasets, ("2026-07-01", "实验A", "FTP"))
    assert len(scoped) == 2
