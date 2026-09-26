"""Ensamblado de regiones (S4 §8.1.3 y §8.1.6): cada región = cadenas compartidas enlazadas en trazados cerrados."""
from dataclasses import dataclass, field

import numpy as np

from app.modules.vectorize.fit import seg_points, seg_reverse


@dataclass
class Loop:
    segs: list
    area: float          # área con signo (shoelace)
    outer: bool = True


@dataclass
class Region:
    label: int
    color: str           # #rrggbb
    lab: tuple
    loops: list[Loop] = field(default_factory=list)

    def filled_area(self) -> float:
        return sum(abs(l.area) for l in self.loops if l.outer)


def _shoelace(segs) -> float:
    pts = np.vstack([seg_points(s, 6)[:-1] for s in segs])
    x, y = pts[:, 0], pts[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def assemble(chains, fitted, labels_meta) -> list[Region]:
    """`fitted[i]`: lista de segmentos de la cadena i (con `left` a la izquierda). `labels_meta`: {etiqueta: (hex, lab)}."""
    by_region: dict[int, list] = {}
    for i, c in enumerate(chains):
        for lab, rev in ((c.left, False), (c.right, True)):
            if lab >= 0:
                segs = fitted[i]
                # la región `left` recorre la cadena tal cual; la `right` la recorre al revés
                by_region.setdefault(lab, []).append((c.v1 if rev else c.v0, c.v0 if rev else c.v1,
                                                      [seg_reverse(s) for s in segs[::-1]] if rev else segs))
    regions = []
    for lab, items in by_region.items():
        starts: dict[int, list[int]] = {}
        for k, (a, b, _) in enumerate(items):
            starts.setdefault(a, []).append(k)
        used = [False] * len(items)
        loops = []
        for k0 in range(len(items)):
            if used[k0]:
                continue
            segs, k = [], k0
            first_start = items[k0][0]
            while True:
                used[k] = True
                segs += items[k][2]
                end = items[k][1]
                if end == first_start:
                    break
                nxt = [j for j in starts.get(end, []) if not used[j]]
                if not nxt:
                    break
                k = nxt[0]
            if segs:
                loops.append(Loop(segs, _shoelace(segs)))
        if loops:
            ref = max(loops, key=lambda l: abs(l.area))
            for l in loops:
                l.outer = (l.area >= 0) == (ref.area >= 0)
            hexc, labc = labels_meta[lab]
            regions.append(Region(lab, hexc, labc, loops))
    return regions
