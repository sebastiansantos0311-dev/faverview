"""Ciencia del color: sRGB ↔ XYZ ↔ Lab (D50, adaptación Bradford), ΔE76/ΔE2000 vectorizados, densidad aproximada y
modelo de mezcla de tintas (orientativo, no espectral).

Todas las funciones aceptan arrays NumPy de cualquier forma con el último eje = 3 (o escalares en tupla)."""
import numpy as np

# Blancos de referencia (XYZ con Y = 1)
D65 = np.array([0.95047, 1.00000, 1.08883])
D50 = np.array([0.96422, 1.00000, 0.82521])

# sRGB (D65) → XYZ (IEC 61966-2-1)
_M_RGB2XYZ = np.array([[0.4124564, 0.3575761, 0.1804375],
                       [0.2126729, 0.7151522, 0.0721750],
                       [0.0193339, 0.1191920, 0.9503041]])
_M_XYZ2RGB = np.linalg.inv(_M_RGB2XYZ)

# Adaptación cromática Bradford
_BRADFORD = np.array([[0.8951, 0.2664, -0.1614],
                      [-0.7502, 1.7135, 0.0367],
                      [0.0389, -0.0685, 1.0296]])


def _adapt_matrix(src_white, dst_white):
    s = _BRADFORD @ src_white
    d = _BRADFORD @ dst_white
    return np.linalg.inv(_BRADFORD) @ np.diag(d / s) @ _BRADFORD


_M_D65_D50 = _adapt_matrix(D65, D50)
_M_D50_D65 = _adapt_matrix(D50, D65)


def _arr(x):
    return np.asarray(x, dtype=np.float64)


# ---------------------------------------------------------------- sRGB ↔ lineal ↔ XYZ ↔ Lab
def srgb_to_linear(rgb):
    """sRGB 0–1 → RGB lineal 0–1."""
    c = _arr(rgb)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(lin):
    c = np.clip(_arr(lin), 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def srgb_to_xyz(rgb, white=D50):
    """sRGB 0–1 → XYZ adaptado al blanco `white` (D50 por defecto, el de impresión)."""
    xyz = srgb_to_linear(rgb) @ _M_RGB2XYZ.T
    return xyz @ _M_D65_D50.T if white is D50 else xyz


def xyz_to_srgb(xyz, white=D50):
    xyz = _arr(xyz)
    if white is D50:
        xyz = xyz @ _M_D50_D65.T
    return linear_to_srgb(xyz @ _M_XYZ2RGB.T)


def xyz_to_lab(xyz, white=D50):
    t = _arr(xyz) / white
    eps, kappa = 216 / 24389, 24389 / 27
    f = np.where(t > eps, np.cbrt(t), (kappa * t + 16) / 116)
    L = 116 * f[..., 1] - 16
    a = 500 * (f[..., 0] - f[..., 1])
    b = 200 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], axis=-1)


def lab_to_xyz(lab, white=D50):
    lab = _arr(lab)
    fy = (lab[..., 0] + 16) / 116
    fx = fy + lab[..., 1] / 500
    fz = fy - lab[..., 2] / 200
    eps, kappa = 216 / 24389, 24389 / 27
    xr = np.where(fx ** 3 > eps, fx ** 3, (116 * fx - 16) / kappa)
    yr = np.where(lab[..., 0] > kappa * eps, fy ** 3, lab[..., 0] / kappa)
    zr = np.where(fz ** 3 > eps, fz ** 3, (116 * fz - 16) / kappa)
    return np.stack([xr, yr, zr], axis=-1) * white


def srgb_to_lab(rgb):
    """sRGB 0–1 → Lab D50."""
    return xyz_to_lab(srgb_to_xyz(rgb))


def lab_to_srgb(lab):
    """Lab D50 → sRGB 0–1 (recortado). Vista aproximada: el color de impresión no cabe siempre en sRGB."""
    return xyz_to_srgb(lab_to_xyz(lab))


def lab_to_hex(lab) -> str:
    r, g, b = (np.clip(np.rint(lab_to_srgb(lab) * 255), 0, 255)).astype(int)
    return f"#{r:02X}{g:02X}{b:02X}"


# ---------------------------------------------------------------- diferencias de color
def delta_e76(lab1, lab2):
    return np.linalg.norm(_arr(lab1) - _arr(lab2), axis=-1)


def delta_e2000(lab1, lab2, kL=1.0, kC=1.0, kH=1.0):
    """CIEDE2000 (Sharma, Wu, Dalal 2005), vectorizado. Valida contra los 34 pares de referencia del artículo."""
    lab1, lab2 = _arr(lab1), _arr(lab2)
    L1, a1, b1 = lab1[..., 0], lab1[..., 1], lab1[..., 2]
    L2, a2, b2 = lab2[..., 0], lab2[..., 1], lab2[..., 2]
    C1, C2 = np.hypot(a1, b1), np.hypot(a2, b2)
    Cbar = (C1 + C2) / 2
    G = 0.5 * (1 - np.sqrt(Cbar ** 7 / (Cbar ** 7 + 25.0 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360
    dLp, dCp = L2 - L1, C2p - C1p
    dh = h2p - h1p
    dh = np.where(dh > 180, dh - 360, np.where(dh < -180, dh + 360, dh))
    dh = np.where((C1p * C2p) == 0, 0.0, dh)
    dHp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dh / 2))
    Lbp = (L1 + L2) / 2
    Cbp = (C1p + C2p) / 2
    hsum = h1p + h2p
    hbp = np.where(np.abs(h1p - h2p) <= 180, hsum / 2, np.where(hsum < 360, (hsum + 360) / 2, (hsum - 360) / 2))
    hbp = np.where((C1p * C2p) == 0, hsum, hbp)
    T = (1 - 0.17 * np.cos(np.radians(hbp - 30)) + 0.24 * np.cos(np.radians(2 * hbp))
         + 0.32 * np.cos(np.radians(3 * hbp + 6)) - 0.20 * np.cos(np.radians(4 * hbp - 63)))
    dTheta = 30 * np.exp(-(((hbp - 275) / 25) ** 2))
    Rc = 2 * np.sqrt(Cbp ** 7 / (Cbp ** 7 + 25.0 ** 7))
    Sl = 1 + 0.015 * (Lbp - 50) ** 2 / np.sqrt(20 + (Lbp - 50) ** 2)
    Sc = 1 + 0.045 * Cbp
    Sh = 1 + 0.015 * Cbp * T
    Rt = -np.sin(np.radians(2 * dTheta)) * Rc
    return np.sqrt((dLp / (kL * Sl)) ** 2 + (dCp / (kC * Sc)) ** 2 + (dHp / (kH * Sh)) ** 2
                   + Rt * (dCp / (kC * Sc)) * (dHp / (kH * Sh)))


# ---------------------------------------------------------------- densidad (orientativa)
def density_status_t(rgb, channel: str = "visual"):
    """Densidad aproximada tipo estado T desde sRGB 0–1: D = −log10(reflectancia).
    `channel`: 'c' (rojo), 'm' (verde), 'y' (azul) o 'visual' (luminancia). Orientativa, no sustituye a un densitómetro."""
    lin = np.clip(srgb_to_linear(rgb), 1e-4, 1.0)
    idx = {"c": 0, "m": 1, "y": 2}
    if channel in idx:
        r = lin[..., idx[channel]]
    else:
        r = lin @ _M_RGB2XYZ[1]
    return -np.log10(np.clip(r, 1e-4, 1.0))


# ---------------------------------------------------------------- modelo de mezcla de tintas (S3 §7.3)
# Espacio de trabajo de la mezcla: ProPhoto RGB lineal (D50). Es lo bastante ancho para contener las tintas de
# impresión (un cian FOGRA queda fuera de sRGB); en sRGB habría valores negativos y el modelo se desharía.
_M_PP2XYZ = np.array([[0.7976749, 0.1351917, 0.0313534],
                      [0.2880402, 0.7118741, 0.0000857],
                      [0.0000000, 0.0000000, 0.8252100]])
_M_XYZ2PP = np.linalg.inv(_M_PP2XYZ)


def _lab_to_lin(lab):
    """Lab D50 → RGB lineal ProPhoto (reflectancia aproximada por canal)."""
    return np.clip(lab_to_xyz(lab) @ _M_XYZ2PP.T, 1e-4, 1.5)


def _lin_to_lab(lin):
    return xyz_to_lab(_arr(lin) @ _M_PP2XYZ.T)


def mix_inks(substrate_lab, inks: list[dict], coverages, n: float = 1.7, paper_lab=(95.0, 0.0, -2.0), output: str = "lab"):
    """Color resultante (Lab D50) de imprimir tintas sobre un sustrato.

    `inks`: lista en orden de impresión de {"lab": (L,a,b) del sólido sobre papel blanco, "opacity": 0–1};
    `coverages`: cobertura 0–1 de cada tinta (escalar o array; todas con la misma forma).
    Modelo (orientativo, no espectral): en RGB lineal, con el factor n de Yule–Nielsen (R^(1/n)):
    - tinta transparente: R = R_sustrato · (1 − t·(1 − T_i)), T_i = R_i / R_papel (transmitancia del sólido);
    - tinta opaca (blanco, metálicos): composición «over» con alfa = t · opacidad.
    t = 0 devuelve el sustrato; t = 1 con sustrato = papel devuelve el sólido de la tinta."""
    sub = _lab_to_lin(substrate_lab) ** (1.0 / n)
    paper = _lab_to_lin(paper_lab) ** (1.0 / n)
    cov = [np.clip(_arr(c), 0.0, 1.0) for c in coverages]
    cur = np.broadcast_to(sub, cov[0].shape + (3,)).copy() if cov else sub.copy()
    for ink, t in zip(inks, cov):
        solid = _lab_to_lin(ink["lab"]) ** (1.0 / n)
        op = float(ink.get("opacity", 0.0))
        t3 = t[..., None]
        trans = np.clip(solid / paper, 0.0, 1.5)
        transparent = cur * (1 - t3 * (1 - trans))
        if op > 0:
            alpha = np.clip(t3 * op, 0.0, 1.0)
            opaque = alpha * solid + (1 - alpha) * cur
            cur = np.where(op >= 0.999, opaque, (1 - op) * transparent + op * opaque)
        else:
            cur = transparent
    if output == "srgb":  # directo a sRGB 0–1 (vista simulada), sin pasar por Lab
        return xyz_to_srgb((cur ** n) @ _M_PP2XYZ.T)
    return _lin_to_lab(cur ** n)
