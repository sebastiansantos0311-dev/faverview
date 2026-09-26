"""Fronteras compartidas (S4 §8.1.4): grafo de bordes de grieta entre píxeles de etiquetas distintas.

Cada cadena une dos nodos (puntos donde se tocan ≥ 3 regiones o el borde de la imagen) y separa exactamente dos regiones;
se ajusta una sola vez y ambas regiones usan la misma curva → no puede haber huecos ni solapes."""
from dataclasses import dataclass

import numpy as np


@dataclass
class Chain:
    pts: np.ndarray          # (n, 2) vértices (x, y) en px de la imagen; recorridos con `left` a la izquierda
    left: int                # etiqueta a la izquierda del recorrido (-1 = exterior de la imagen)
    right: int
    closed: bool             # cadena cerrada sin nodos (isla aislada)
    v0: int                  # id del vértice inicial y final (para enlazar)
    v1: int


def build_chains(L: np.ndarray) -> list[Chain]:
    H, W = L.shape
    P = np.full((H + 2, W + 2), -1, np.int32)
    P[1:-1, 1:-1] = L
    W1 = W + 1
    # grietas horizontales (en y = a, de x = c a c+1): arriba = izquierda al ir hacia +x
    up, dn = P[:-1, 1:-1], P[1:, 1:-1]
    hy, hx = np.nonzero(up != dn)
    # grietas verticales (en x = b, de y = r a r+1): el píxel de la derecha queda a la izquierda al ir hacia +y
    lf, rt = P[1:-1, :-1], P[1:-1, 1:]
    vy, vx = np.nonzero(lf != rt)
    v0 = np.concatenate([hy * W1 + hx, vy * W1 + vx])
    v1 = np.concatenate([hy * W1 + hx + 1, (vy + 1) * W1 + vx])
    left = np.concatenate([up[hy, hx], rt[vy, vx]])
    right = np.concatenate([dn[hy, hx], lf[vy, vx]])
    E = len(v0)
    if E == 0:
        return []
    inc: dict[int, list[int]] = {}
    for e in range(E):
        inc.setdefault(int(v0[e]), []).append(e)
        inc.setdefault(int(v1[e]), []).append(e)
    visited = np.zeros(E, bool)
    chains: list[Chain] = []

    def xy(v):
        return (v % W1, v // W1)

    def walk(start_v: int, e: int, closed: bool):
        verts = [start_v]
        cur = start_v
        first = e
        forward_first = int(v0[e]) == start_v
        while True:
            visited[e] = True
            nxt = int(v1[e]) if int(v0[e]) == cur else int(v0[e])
            verts.append(nxt)
            cur = nxt
            edges_here = inc[cur]
            if len(edges_here) != 2 or cur == start_v:
                break
            e = edges_here[1] if edges_here[0] == e else edges_here[0]
            if visited[e]:
                break
        lft, rgt = (int(left[first]), int(right[first])) if forward_first else (int(right[first]), int(left[first]))
        pts = np.array([xy(v) for v in verts], np.float64)
        chains.append(Chain(pts, lft, rgt, closed and verts[0] == verts[-1] and len(inc[verts[0]]) == 2, verts[0], verts[-1]))

    node_vs = [v for v, es in inc.items() if len(es) != 2]
    for v in node_vs:
        for e in inc[v]:
            if not visited[e]:
                walk(v, e, False)
    for e in range(E):                       # lo que queda son bucles sin nodos (islas o huecos aislados)
        if not visited[e]:
            walk(int(v0[e]), e, True)
    return chains
