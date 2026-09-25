import numpy as np

from app.align import align_images
from app.compare_visual import compare_visual
from app.config import load_config


def _base():
    img = np.full((600, 800, 3), 255, np.uint8)
    img[100:200, 100:300] = (30, 90, 200)
    img[300:340, 100:600] = (40, 40, 40)
    return img


def test_identical_image_scores_at_least_99():
    a = _base()
    r = compare_visual(a, a.copy(), load_config())
    assert r.score * 100 >= 99 and not r.differences


def test_added_rectangle_is_one_region():
    a = _base()
    b = a.copy()
    b[450:520, 500:700] = (220, 30, 30)
    r = compare_visual(a, b, load_config())
    assert len(r.differences) == 1
    x, y, w, h = r.differences[0].bbox
    assert x <= 500 and y <= 450 and x + w >= 700 and y + h >= 520


def test_alignment_recovers_small_rotation():
    import cv2
    rng = np.random.default_rng(1)
    a = _base()
    for _ in range(60):
        x, y = rng.integers(0, 700), rng.integers(0, 500)
        a[y:y + 20, x:x + 30] = rng.integers(0, 255, 3)
    m = cv2.getRotationMatrix2D((400, 300), 2.0, 1.0)
    b = cv2.warpAffine(a, m, (800, 600), borderValue=(255, 255, 255))
    res = align_images(a, b)
    assert res.aligned
    assert compare_visual(a, res.aligned_client, load_config()).score > 0.9


def test_manual_alignment_with_four_points():
    import cv2
    a = _base()
    m = cv2.getRotationMatrix2D((400, 300), 3.0, 1.0)
    b = cv2.warpAffine(a, m, (800, 600), borderValue=(255, 255, 255))
    src = np.float32([[100, 100], [700, 100], [700, 500], [100, 500]])          # puntos en el diseño
    moved = cv2.transform(src.reshape(-1, 1, 2), m).reshape(-1, 2)              # dónde caen en el cliente
    from app.align import align_images
    res = align_images(a, b, {"client": moved.tolist(), "design": src.tolist()})
    assert res.method == "manual"
    assert compare_visual(a, res.aligned_client, load_config(), res.valid_mask).score > 0.95


def test_stripping_a_screenshot_frame():
    from app.align import strip_frame
    a = _base()
    framed = np.full((a.shape[0] + 100, a.shape[1] + 40, 3), (32, 33, 36), np.uint8)
    framed[60:60 + a.shape[0], 20:20 + a.shape[1]] = a
    out, _ = strip_frame(framed, a)
    assert abs(out.shape[0] - a.shape[0]) <= 4 and abs(out.shape[1] - a.shape[1]) <= 4
    assert strip_frame(a, a)[0].shape == a.shape  # sin marco no se recorta nada
