"""Evaluación de funciones PDF (tipos 0, 2, 3 y 4) para obtener el color alternativo de una tinta directa.

Se usa para evaluar la *tint transform* de los espacios Separation/DeviceN. El tipo 4 (calculadora PostScript) soporta el
subconjunto definido por la especificación de PDF (aritmética, pila, comparaciones, if/ifelse)."""
import itertools
import math

import numpy as np
import pikepdf


class FunctionError(Exception):
    pass


def _clip(x, rng):
    if rng is None:
        return x
    r = np.array([float(v) for v in rng]).reshape(-1, 2)
    return [min(max(v, r[i][0]), r[i][1]) for i, v in enumerate(x)]


def evaluate(fn, inputs) -> list[float]:
    """Evalúa una función PDF (objeto pikepdf o lista de funciones) con `inputs`."""
    if isinstance(fn, pikepdf.Array):  # varias funciones de 1 salida (una por componente)
        out = []
        for f in fn:
            out += evaluate(f, inputs)
        return out
    ftype = int(fn.get("/FunctionType", -1))
    dom = fn.get("/Domain")
    x = _clip(list(inputs), dom) if dom is not None else list(inputs)
    rng = fn.get("/Range")
    if ftype == 2:
        c0 = [float(v) for v in fn.get("/C0", [0.0])]
        c1 = [float(v) for v in fn.get("/C1", [1.0])]
        n = float(fn.get("/N", 1))
        t = x[0]
        y = [a + (t ** n) * (b - a) for a, b in zip(c0, c1)]
    elif ftype == 3:
        fns = list(fn["/Functions"])
        bounds = [float(v) for v in fn.get("/Bounds", [])]
        enc = [float(v) for v in fn["/Encode"]]
        d0, d1 = float(dom[0]), float(dom[1])
        t = x[0]
        k = sum(1 for b in bounds if t >= b)
        k = min(k, len(fns) - 1)
        lo = d0 if k == 0 else bounds[k - 1]
        hi = d1 if k == len(fns) - 1 else bounds[k]
        e0, e1 = enc[2 * k], enc[2 * k + 1]
        tt = e0 if hi == lo else e0 + (t - lo) * (e1 - e0) / (hi - lo)
        y = evaluate(fns[k], [tt])
    elif ftype == 0:
        y = _sampled(fn, x)
    elif ftype == 4:
        y = _postscript(fn, x)
    else:
        raise FunctionError(f"Tipo de función no soportado: {ftype}")
    return _clip(y, rng) if rng is not None else y


def _sampled(fn, x):
    size = [int(v) for v in fn["/Size"]]
    bps = int(fn["/BitsPerSample"])
    dom = [float(v) for v in fn["/Domain"]]
    rng = [float(v) for v in fn["/Range"]]
    m, n = len(size), len(rng) // 2
    enc = [float(v) for v in fn["/Encode"]] if "/Encode" in fn else [v for s in size for v in (0, s - 1)]
    dec = [float(v) for v in fn["/Decode"]] if "/Decode" in fn else rng
    data = fn.read_bytes()
    total = int(np.prod(size)) * n
    if bps == 8:
        samples = np.frombuffer(data, np.uint8)[:total].astype(float)
    elif bps == 16:
        samples = np.frombuffer(data, ">u2")[:total].astype(float)
    else:
        bits = np.unpackbits(np.frombuffer(data, np.uint8))
        vals = bits[: total * bps].reshape(-1, bps)
        samples = (vals * (1 << np.arange(bps - 1, -1, -1))).sum(axis=1).astype(float)
    maxv = float((1 << bps) - 1)
    e = []
    for i in range(m):
        d0, d1 = dom[2 * i], dom[2 * i + 1]
        v = enc[2 * i] + (x[i] - d0) * (enc[2 * i + 1] - enc[2 * i]) / ((d1 - d0) or 1.0)
        e.append(min(max(v, 0.0), size[i] - 1))
    lo = [int(math.floor(v)) for v in e]
    fr = [v - l for v, l in zip(e, lo)]
    acc = np.zeros(n)
    strides = [int(np.prod(size[:i])) for i in range(m)]
    for corner in itertools.product((0, 1), repeat=m):
        w = 1.0
        idx = 0
        for i, c in enumerate(corner):
            w *= fr[i] if c else (1 - fr[i])
            idx += min(lo[i] + c, size[i] - 1) * strides[i]
        if w:
            acc += w * samples[idx * n:(idx + 1) * n]
    return [dec[2 * j] + acc[j] * (dec[2 * j + 1] - dec[2 * j]) / maxv for j in range(n)]


def _tokens(src: str):
    src = src.replace("{", " { ").replace("}", " } ")
    return src.split()


def _parse(tokens, i=0):
    """Devuelve (lista de tokens/bloques, siguiente índice) para un bloque `{ ... }`."""
    out = []
    while i < len(tokens):
        t = tokens[i]
        if t == "{":
            blk, i = _parse(tokens, i + 1)
            out.append(blk)
        elif t == "}":
            return out, i + 1
        else:
            out.append(t)
            i += 1
    return out, i


def _run(prog, st):
    i = 0
    while i < len(prog):
        t = prog[i]
        i += 1
        if isinstance(t, list):
            nxt = prog[i] if i < len(prog) else None
            if nxt == "if":
                if st.pop():
                    _run(t, st)
                i += 1
            elif isinstance(nxt, list) and i + 1 < len(prog) and prog[i + 1] == "ifelse":
                _run(t if st.pop() else nxt, st)
                i += 2
            else:
                raise FunctionError("Bloque PostScript sin if/ifelse")
            continue
        try:
            st.append(float(t))
            continue
        except ValueError:
            pass
        _op(t, st)


def _op(t, st):
    def two():
        b, a = st.pop(), st.pop()
        return a, b
    if t == "add": a, b = two(); st.append(a + b)
    elif t == "sub": a, b = two(); st.append(a - b)
    elif t == "mul": a, b = two(); st.append(a * b)
    elif t == "div": a, b = two(); st.append(a / b if b else 0.0)
    elif t == "idiv": a, b = two(); st.append(float(int(a) // int(b)) if int(b) else 0.0)
    elif t == "mod": a, b = two(); st.append(float(int(a) % int(b)) if int(b) else 0.0)
    elif t == "neg": st.append(-st.pop())
    elif t == "abs": st.append(abs(st.pop()))
    elif t == "ceiling": st.append(float(math.ceil(st.pop())))
    elif t == "floor": st.append(float(math.floor(st.pop())))
    elif t == "round": st.append(float(math.floor(st.pop() + 0.5)))
    elif t == "truncate": st.append(float(math.trunc(st.pop())))
    elif t == "sqrt": st.append(math.sqrt(max(st.pop(), 0.0)))
    elif t == "sin": st.append(math.sin(math.radians(st.pop())))
    elif t == "cos": st.append(math.cos(math.radians(st.pop())))
    elif t == "atan": a, b = two(); st.append(math.degrees(math.atan2(a, b)) % 360)
    elif t == "exp": a, b = two(); st.append(a ** b)
    elif t == "ln": st.append(math.log(max(st.pop(), 1e-12)))
    elif t == "log": st.append(math.log10(max(st.pop(), 1e-12)))
    elif t in ("cvi", "cvr"): st.append(float(int(st.pop())) if t == "cvi" else st.pop())
    elif t == "pop": st.pop()
    elif t == "exch": st[-1], st[-2] = st[-2], st[-1]
    elif t == "dup": st.append(st[-1])
    elif t == "copy":
        n = int(st.pop())
        if n > 0:
            st.extend(st[-n:])
    elif t == "index": n = int(st.pop()); st.append(st[-1 - n])
    elif t == "roll":
        j, n = int(st.pop()), int(st.pop())
        if n > 0:
            j %= n
            if j:
                seg = st[-n:]
                st[-n:] = seg[-j:] + seg[:-j]
    elif t in ("eq", "ne", "gt", "ge", "lt", "le"):
        a, b = two()
        st.append(float({"eq": a == b, "ne": a != b, "gt": a > b, "ge": a >= b, "lt": a < b, "le": a <= b}[t]))
    elif t == "and": a, b = two(); st.append(float(int(a) & int(b)))
    elif t == "or": a, b = two(); st.append(float(int(a) | int(b)))
    elif t == "xor": a, b = two(); st.append(float(int(a) ^ int(b)))
    elif t == "not": v = st.pop(); st.append(float(not v) if v in (0.0, 1.0) else float(~int(v)))
    elif t == "bitshift": a, b = two(); st.append(float(int(a) << int(b) if b >= 0 else int(a) >> int(-b)))
    elif t == "true": st.append(1.0)
    elif t == "false": st.append(0.0)
    else:
        raise FunctionError(f"Operador PostScript no soportado: {t}")


def _postscript(fn, x):
    toks = _tokens(fn.read_bytes().decode("latin-1"))
    prog, _ = _parse(toks, 0)
    if len(prog) == 1 and isinstance(prog[0], list):
        prog = prog[0]
    st = [float(v) for v in x]
    try:
        _run(prog, st)
    except (IndexError, ZeroDivisionError, ValueError) as e:
        raise FunctionError(f"Función PostScript inválida: {e}")
    n = len(fn["/Range"]) // 2
    if len(st) < n:
        raise FunctionError("La función PostScript dejó menos valores de los esperados.")
    return st[-n:]
