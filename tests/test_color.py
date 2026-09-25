import numpy as np

from app.compare_color import delta_e_hex, grid_color_diffs


def test_red_vs_darker_red_is_detected():
    assert delta_e_hex("#FF0000", "#CC0000") > 10


def test_almost_identical_red_is_not_detected():
    assert delta_e_hex("#FF0000", "#FE0101") < 10


def test_grid_detects_changed_zone():
    a = np.full((320, 320, 3), 255, np.uint8)
    a[64:192, 64:192] = (255, 0, 0)
    b = a.copy()
    b[64:192, 64:192] = (204, 0, 0)
    diffs, area = grid_color_diffs(a, b, [], 10)
    assert len(diffs) == 1 and area > 0
    same, _ = grid_color_diffs(a, a.copy(), [], 10)
    assert not same
