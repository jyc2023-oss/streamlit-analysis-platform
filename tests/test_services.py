import numpy as np

from src.services.datasets import (
    downsample,
    filter_datasets_by_folder,
    folder_choices,
    latest_complete_dataset_pair,
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


def test_latest_complete_dataset_pair_prefers_newest_ready_folder() -> None:
    def item(path: str, channels: int, modified_at: str, status: str = "ready") -> dict:
        return {
            "relative_path": path,
            "name": path.rsplit("/", 1)[-1],
            "modified_at": modified_at,
            "status": status,
            "metadata": {"channels_count": channels},
        }

    datasets = [
        item("2026-07-20/A/NET9770_114/a.bin", 8, "2026-07-20T09:00:00+00:00"),
        item("2026-07-20/A/NET9770_116/b.bin", 2, "2026-07-20T09:00:01+00:00"),
        item("2026-07-21/B/NET9770_114/c.bin", 8, "2026-07-21T09:00:00+00:00"),
        item("2026-07-21/B/NET9770_116/d.bin", 2, "2026-07-21T09:00:01+00:00"),
        item(
            "2026-07-22/C/NET9770_116/e.bin",
            2,
            "2026-07-22T09:00:00+00:00",
            status="pending",
        ),
    ]

    pair = latest_complete_dataset_pair(datasets)

    assert pair is not None
    scope, selected_8, selected_2 = pair
    assert scope == ("2026-07-21", "B")
    assert selected_8["name"] == "c.bin"
    assert selected_2["name"] == "d.bin"
