from __future__ import annotations

from typing import Any


def clicked_cycle_from_points(
    points: list[dict[str, Any]],
    starts: list[int],
    cycle_points: int,
    sample_rate: float,
) -> tuple[int | None, tuple[int, int, int] | None]:
    """Map a selected Plotly point to the nearest detected 50 Hz cycle."""
    for point in reversed(points):
        clicked_start = None
        customdata = point.get("customdata")
        if isinstance(customdata, (list, tuple)) and customdata:
            candidate = int(customdata[0])
            if candidate in starts:
                clicked_start = candidate
        if clicked_start is None and point.get("x") is not None and starts:
            click_sample = float(point["x"]) * sample_rate
            clicked_start = min(
                starts,
                key=lambda start: abs(start + cycle_points / 2 - click_sample),
            )
        if clicked_start is not None:
            signature = (
                int(point.get("curve_number", -1)),
                int(point.get("point_number", -1)),
                clicked_start,
            )
            return clicked_start, signature
    return None, None


def apply_cycle_click(
    noarc: list[int],
    arc: list[int],
    clicked_start: int,
    target: str,
    maximum: int,
) -> tuple[list[int], list[int], str | None]:
    """Apply one manual chart click while enforcing counts and disjoint classes."""
    updated_noarc = list(noarc)
    updated_arc = list(arc)
    if target == "取消选择":
        return (
            [item for item in updated_noarc if item != clicked_start],
            [item for item in updated_arc if item != clicked_start],
            None,
        )
    target_values = updated_noarc if target == "无弧" else updated_arc
    other_values = updated_arc if target == "无弧" else updated_noarc
    if clicked_start in other_values:
        return updated_noarc, updated_arc, "这个周波已属于另一类别，请先取消选择。"
    if clicked_start in target_values:
        target_values.remove(clicked_start)
        return updated_noarc, updated_arc, None
    if len(target_values) >= maximum:
        return updated_noarc, updated_arc, f"{target}已经选满 {maximum} 个周波。"
    target_values.append(clicked_start)
    return updated_noarc, updated_arc, None
