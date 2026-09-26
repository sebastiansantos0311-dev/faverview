import numpy as np
import pytest
from skimage.color import deltaE_ciede2000, rgb2lab

from app.core import colorscience as cs
from app.core import units

# 34 pares de referencia de Sharma, Wu y Dalal (2005): (Lab1, Lab2, ΔE00 esperado)
SHARMA = [
    ((50.0000, 2.6772, -79.7751), (50.0000, 0.0000, -82.7485), 2.0425),
    ((50.0000, 3.1571, -77.2803), (50.0000, 0.0000, -82.7485), 2.8615),
    ((50.0000, 2.8361, -74.0200), (50.0000, 0.0000, -82.7485), 3.4412),
    ((50.0000, -1.3802, -84.2814), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, -1.1848, -84.8006), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, -0.9009, -85.5211), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, 0.0000, 0.0000), (50.0000, -1.0000, 2.0000), 2.3669),
    ((50.0000, -1.0000, 2.0000), (50.0000, 0.0000, 0.0000), 2.3669),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0009), 7.1792),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0010), 7.1792),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0011), 7.2195),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0012), 7.2195),
    ((50.0000, -0.0010, 2.4900), (50.0000, 0.0009, -2.4900), 4.8045),
    ((50.0000, -0.0010, 2.4900), (50.0000, 0.0010, -2.4900), 4.8045),
    ((50.0000, -0.0010, 2.4900), (50.0000, 0.0011, -2.4900), 4.7461),
    ((50.0000, 2.5000, 0.0000), (50.0000, 0.0000, -2.5000), 4.3065),
    ((50.0000, 2.5000, 0.0000), (73.0000, 25.0000, -18.0000), 27.1492),
    ((50.0000, 2.5000, 0.0000), (61.0000, -5.0000, 29.0000), 22.8977),
    ((50.0000, 2.5000, 0.0000), (56.0000, -27.0000, -3.0000), 31.9030),
    ((50.0000, 2.5000, 0.0000), (58.0000, 24.0000, 15.0000), 19.4535),
    ((50.0000, 2.5000, 0.0000), (50.0000, 3.1736, 0.5854), 1.0000),
    ((50.0000, 2.5000, 0.0000), (50.0000, 3.2972, 0.0000), 1.0000),
    ((50.0000, 2.5000, 0.0000), (50.0000, 1.8634, 0.5757), 1.0000),
    ((50.0000, 2.5000, 0.0000), (50.0000, 3.2592, 0.3350), 1.0000),
    ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
    ((63.0109, -31.0961, -5.8663), (62.8187, -29.7946, -4.0864), 1.2630),
    ((61.2901, 3.7196, -5.3901), (61.4292, 2.2480, -4.9620), 1.8731),
    ((35.0831, -44.1164, 3.7933), (35.0232, -40.0716, 1.5901), 1.8645),
    ((22.7233, 20.0904, -46.6940), (23.0331, 14.9730, -42.5619), 2.0373),
    ((36.4612, 47.8580, 18.3852), (36.2715, 50.5065, 21.2231), 1.4146),
    ((90.8027, -2.0831, 1.4410), (91.1528, -1.6435, 0.0447), 1.4441),
    ((90.9257, -0.5406, -0.9208), (88.6381, -0.8985, -0.7239), 1.5381),
    ((6.7747, -0.2908, -2.4247), (5.8714, -0.0985, -2.2286), 0.6377),
    ((2.0776, 0.0795, -1.1350), (0.9033, -0.0636, -0.5514), 0.9082),
]


def test_units_exact():
    assert units.in_to_mm(1) == 25.4 and units.mm_to_pt(25.4) == pytest.approx(72.0)
    assert units.pt_to_mm(72) == pytest.approx(25.4)
    assert units.px_to_mm(300, 300) == pytest.approx(25.4) and units.mm_to_px(25.4, 600) == pytest.approx(600)
    assert units.ppi_at_size(300, 25.4) == pytest.approx(300)
    assert units.pt_to_px(72, 200) == pytest.approx(200) and units.px_to_pt(200, 200) == pytest.approx(72)


def test_delta_e2000_matches_sharma_reference_pairs():
    a = np.array([p[0] for p in SHARMA]); b = np.array([p[1] for p in SHARMA]); exp = np.array([p[2] for p in SHARMA])
    got = cs.delta_e2000(a, b)
    assert len(SHARMA) == 34
    assert np.max(np.abs(got - exp)) < 1e-4


def test_delta_e2000_agrees_with_scikit_image_on_random_lab():
    rng = np.random.default_rng(3)
    a = np.column_stack([rng.uniform(0, 100, 500), rng.uniform(-90, 90, 500), rng.uniform(-90, 90, 500)])
    b = np.column_stack([rng.uniform(0, 100, 500), rng.uniform(-90, 90, 500), rng.uniform(-90, 90, 500)])
    assert np.max(np.abs(cs.delta_e2000(a, b) - deltaE_ciede2000(a, b))) < 1e-6
    assert np.allclose(cs.delta_e76([0, 0, 0], [3, 4, 0]), 5.0)


def test_srgb_lab_roundtrip_and_known_values():
    rgb = np.array([[1, 1, 1], [0, 0, 0], [1, 0, 0], [0.2, 0.5, 0.8]])
    lab = cs.srgb_to_lab(rgb)
    assert lab[0] == pytest.approx([100, 0, 0], abs=0.05)                 # blanco D50
    assert lab[1] == pytest.approx([0, 0, 0], abs=1e-6)
    assert lab[2] == pytest.approx([54.29, 80.81, 69.89], abs=0.6)        # rojo sRGB en D50 (Bradford)
    assert np.allclose(cs.lab_to_srgb(lab), rgb, atol=1e-6)
    assert cs.lab_to_hex([100, 0, 0]) == "#FFFFFF"
    # coherente con scikit-image (D65) tras adaptar: mismo L*
    assert cs.srgb_to_lab(rgb)[3][0] == pytest.approx(rgb2lab(rgb.reshape(1, -1, 3))[0][3][0], abs=1.0)


def test_density_orientativa():
    assert cs.density_status_t([1, 1, 1]) == pytest.approx(0, abs=1e-3)
    assert cs.density_status_t([0.5, 0.5, 0.5], "c") > 0.2
    assert cs.density_status_t([0, 0, 0]) > 3.5


def test_ink_mixing_model_limits():
    paper = (95.0, 0.0, -2.0)
    cyan = {"lab": (55.0, -37.0, -50.0), "opacity": 0.0}
    white = {"lab": (95.0, 0.0, -2.0), "opacity": 1.0}
    assert cs.mix_inks(paper, [cyan], [0.0]) == pytest.approx(paper, abs=1e-6)          # t = 0 → sustrato
    assert cs.mix_inks(paper, [cyan], [1.0]) == pytest.approx(cyan["lab"], abs=0.05)    # t = 1 → sólido
    half = cs.mix_inks(paper, [cyan], [0.5])
    assert 55 < half[0] < 95                                                            # intermedio y monótono
    # sobre prenda negra: el blanco opaco (t=1) la tapa; la cian transparente casi no se ve
    black = (10.0, 0.0, 0.0)
    assert cs.mix_inks(black, [white], [1.0])[0] > 90
    assert cs.mix_inks(black, [cyan], [1.0])[0] < 30
    # vectorizado: distintas coberturas a la vez
    out = cs.mix_inks(paper, [cyan], [np.array([0.0, 0.5, 1.0])])
    assert out.shape == (3, 3) and out[0][0] > out[1][0] > out[2][0]
