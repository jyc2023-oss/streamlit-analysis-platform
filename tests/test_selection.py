from src.analysis.selection import (
    apply_cycle_click,
    clicked_cycle_from_points,
    normalize_cycle_selection,
)


def test_normalize_cycle_selection_accepts_partial_or_complete_disjoint_submission() -> None:
    assert normalize_cycle_selection([100, 200], [300, 400], [100, 200, 300, 400], 2) == (
        [100, 200],
        [300, 400],
    )
    assert normalize_cycle_selection([100], [], [100, 200, 300, 400], 2) == ([100], [])
    assert normalize_cycle_selection([], [], [100, 200, 300, 400], 2) == ([], [])
    assert normalize_cycle_selection([100, 200, 300], [], [100, 200, 300, 400], 2) is None
    assert normalize_cycle_selection([100, 200], [200, 400], [100, 200, 300, 400], 2) is None
    assert normalize_cycle_selection([100, 999], [300, 400], [100, 200, 300, 400], 2) is None


def test_clicked_cycle_uses_customdata_or_nearest_waveform_point() -> None:
    starts = [0, 200, 400]
    clicked, signature = clicked_cycle_from_points(
        [{"curve_number": 4, "point_number": 1, "customdata": [200, 2], "x": 0.03}],
        starts,
        200,
        10_000,
    )
    assert clicked == 200
    assert signature == (4, 1, 200)

    clicked, _ = clicked_cycle_from_points(
        [{"curve_number": 0, "point_number": 9, "x": 0.051}],
        starts,
        200,
        10_000,
    )
    assert clicked == 400


def test_apply_cycle_click_keeps_classes_disjoint_and_enforces_limit() -> None:
    noarc, arc, notice = apply_cycle_click([], [], 100, "无弧", 2)
    assert (noarc, arc, notice) == ([100], [], None)

    noarc, arc, notice = apply_cycle_click(noarc, arc, 100, "有弧", 2)
    assert noarc == [100]
    assert arc == []
    assert notice is not None

    noarc, arc, _ = apply_cycle_click(noarc, arc, 200, "无弧", 2)
    noarc, arc, notice = apply_cycle_click(noarc, arc, 300, "无弧", 2)
    assert noarc == [100, 200]
    assert notice == "无弧已经选满 2 个周波。"

    noarc, arc, notice = apply_cycle_click(noarc, arc, 100, "取消选择", 2)
    assert (noarc, arc, notice) == ([200], [], None)
