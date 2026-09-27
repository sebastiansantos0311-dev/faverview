"""Motor de recetas (S8): ejecutar una receta sobre un archivo, una carpeta o una carpeta vigilada (watchdog)."""
import json
import re
import shutil
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

from app.config import DATOS_DIR
from app.core.errors import UserError
from app.modules.automation import steps as st

BUILTIN_DIR = Path(__file__).with_name("recetas")
USER_DIR = DATOS_DIR / "automatizar" / "recetas"
INPUT_EXT = {".pdf"} | st.IMG_EXT


# ---------------------------------------------------------------- recetas
def step_key(step: dict) -> str:
    a = str(step.get("accion", "")).strip()
    m = str(step.get("modulo", "")).strip()
    return a if "." in a or not m else f"{m}.{a}"


def validate(recipe: dict) -> list[str]:
    """Lista de problemas (vacía = válida)."""
    errs = []
    if not str(recipe.get("nombre", "")).strip():
        errs.append("La receta necesita un nombre.")
    pasos = recipe.get("pasos")
    if not isinstance(pasos, list) or not pasos:
        errs.append("La receta necesita al menos un paso.")
        return errs
    for i, s in enumerate(pasos, 1):
        k = step_key(s) if isinstance(s, dict) else ""
        if k not in st.CATALOG:
            errs.append(f"Paso {i}: la acción «{k or '?'}» no existe.")
            continue
        params = s.get("parametros") or {}
        if not isinstance(params, dict):
            errs.append(f"Paso {i}: «parametros» debe ser un objeto.")
            continue
        for p in params:
            if p not in st.CATALOG[k][3]:
                errs.append(f"Paso {i} ({k}): el parámetro «{p}» no existe.")
    return errs


def _safe(rid: str) -> str:
    if not re.match(r"^[\w\- ]{1,60}$", rid or ""):
        raise UserError("El identificador de la receta solo admite letras, números, espacios, _ y -.")
    return rid


def list_recipes() -> list[dict]:
    out = []
    for d, own in ((BUILTIN_DIR, False), (USER_DIR, True)):
        if d.exists():
            for f in sorted(d.glob("*.json")):
                try:
                    r = json.loads(f.read_text(encoding="utf-8"))
                    out.append({"id": f.stem, "nombre": r.get("nombre", f.stem), "descripcion": r.get("descripcion", ""), "pasos": len(r.get("pasos", [])), "propia": own})
                except Exception:
                    pass
    return out


def load_recipe(rid: str) -> dict:
    for d in (USER_DIR, BUILTIN_DIR):
        f = d / f"{_safe(rid)}.json"
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
    raise UserError("No existe esa receta.")


def save_recipe(rid: str, recipe: dict) -> None:
    errs = validate(recipe)
    if errs:
        raise UserError("La receta no es válida: " + " ".join(errs))
    USER_DIR.mkdir(parents=True, exist_ok=True)
    (USER_DIR / f"{_safe(rid)}.json").write_text(json.dumps(recipe, indent=1, ensure_ascii=False), encoding="utf-8")


def delete_recipe(rid: str) -> None:
    f = USER_DIR / f"{_safe(rid)}.json"
    if not f.exists():
        raise UserError("Solo se pueden borrar tus propias recetas.")
    f.unlink()


def catalog() -> list[dict]:
    return [{"id": k, "entrada": v[1], "descripcion": v[2],
             "parametros": [{"nombre": n, "tipo": t[0], "defecto": t[1], "ayuda": t[2]} for n, t in v[3].items()]} for k, v in st.CATALOG.items()]


# ---------------------------------------------------------------- ejecución
def run_file(recipe: dict, path, out_dir, progress=None) -> dict:
    """Ejecuta la receta sobre un archivo. Devuelve {estado: ok|detenido|error, log, salidas}. Nunca lanza excepciones."""
    path, out_dir = Path(path), Path(out_dir)
    errs = validate(recipe)
    if errs:
        return {"archivo": path.name, "estado": "error", "log": errs, "salidas": [], "motivo": " ".join(errs)}
    ctx = st.Ctx(path, out_dir)
    estado, motivo = "ok", ""
    ctx.say(f"[{datetime.now():%H:%M:%S}] Receta «{recipe.get('nombre')}» sobre {path.name}")
    for i, s in enumerate(recipe["pasos"], 1):
        key = step_key(s)
        fn, need, desc, schema = st.CATALOG[key]
        params = {**{n: t[1] for n, t in schema.items() if t[1] is not None}, **(s.get("parametros") or {})}
        if progress:
            progress(f"Paso {i}/{len(recipe['pasos'])}: {desc}")
        ctx.say(f"Paso {i}: {desc}")
        try:
            fn(ctx, **params)
        except st.StopRecipe as e:
            estado, motivo = "detenido", str(e)
            ctx.say(f"DETENIDO: {motivo}")
            break
        except (st.StepError, UserError) as e:
            estado, motivo = "error", getattr(e, "message", None) or str(e)
            ctx.say(f"ERROR: {motivo}")
            break
        except Exception as e:  # nunca romper el lote por un archivo
            traceback.print_exc()
            estado, motivo = "error", f"Error inesperado ({type(e).__name__}): {e}"
            ctx.say(f"ERROR: {motivo}")
            break
    return {"archivo": path.name, "estado": estado, "motivo": motivo, "log": ctx.log, "salidas": [str(p) for p in ctx.outputs if Path(p).exists()]}


def run_folder(recipe: dict, in_dir, out_root, progress=None, cancel: threading.Event | None = None) -> dict:
    """Procesa todos los archivos de `in_dir`: salida/<archivo>/ para los correctos, errores/ para los que fallan o se detienen."""
    in_dir, out_root = Path(in_dir), Path(out_root)
    if not in_dir.is_dir():
        raise UserError("La carpeta de entrada no existe.")
    files = sorted(p for p in in_dir.iterdir() if p.is_file() and p.suffix.lower() in INPUT_EXT)
    if not files:
        raise UserError("La carpeta no tiene PDF ni imágenes para procesar.")
    results = []
    for n, f in enumerate(files, 1):
        if cancel is not None and cancel.is_set():
            break
        if progress:
            progress(f"Archivo {n}/{len(files)}: {f.name}", n / len(files))
        results.append(process_one(recipe, f, out_root))
    summary = write_summary(results, out_root, recipe)
    return {"archivos": len(files), "ok": sum(r["estado"] == "ok" for r in results), "detenidos": sum(r["estado"] == "detenido" for r in results),
            "errores": sum(r["estado"] == "error" for r in results), "resultados": results, "resumen": str(summary)}


def process_one(recipe: dict, f: Path, out_root: Path) -> dict:
    out_root = Path(out_root)
    work = out_root / "salida" / f.stem
    r = run_file(recipe, f, work)
    logtxt = "\n".join(r["log"])
    if r["estado"] == "ok":
        (work / "registro.txt").write_text(logtxt, encoding="utf-8")
    else:
        err = out_root / "errores"
        err.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(f, err / f.name)
        except OSError:
            pass
        (err / f"{f.stem}.log.txt").write_text(logtxt, encoding="utf-8")
        shutil.rmtree(work, ignore_errors=True)
    rep = out_root / "reportes"
    rep.mkdir(parents=True, exist_ok=True)
    (rep / f"{f.stem}.txt").write_text(logtxt, encoding="utf-8")
    return r


def write_summary(results: list[dict], out_root: Path, recipe: dict) -> Path:
    rep = Path(out_root) / "reportes"
    rep.mkdir(parents=True, exist_ok=True)
    lines = [f"# Resumen del lote — {datetime.now():%Y-%m-%d %H:%M}", f"Receta: {recipe.get('nombre')}", "",
             f"Archivos: {len(results)} · correctos: {sum(r['estado'] == 'ok' for r in results)} · detenidos: "
             f"{sum(r['estado'] == 'detenido' for r in results)} · con error: {sum(r['estado'] == 'error' for r in results)}", ""]
    for r in results:
        lines.append(f"- {r['archivo']}: {r['estado']}" + (f" — {r['motivo']}" if r.get("motivo") else ""))
    p = rep / "resumen.md"
    p.write_text("\n".join(lines), encoding="utf-8")
    (rep / "resumen.json").write_text(json.dumps([{k: v for k, v in r.items() if k != "log"} for r in results], ensure_ascii=False, indent=1), encoding="utf-8")
    return p


# ---------------------------------------------------------------- carpeta vigilada
WATCHERS: dict[str, dict] = {}
_LOCK = threading.Lock()


def _wait_stable(path: Path, tries: int = 20) -> bool:
    last = -1
    for _ in range(tries):
        try:
            size = path.stat().st_size
        except OSError:
            return False
        if size == last and size > 0:
            return True
        last = size
        time.sleep(0.4)
    return False


def start_watch(watch_id: str, recipe: dict, in_dir, out_root) -> dict:
    """Vigila `in_dir`: cada archivo nuevo se procesa con la receta (salida/, errores/, reportes/ dentro de `out_root`)."""
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
    errs = validate(recipe)
    if errs:
        raise UserError("La receta no es válida: " + " ".join(errs))
    in_dir, out_root = Path(in_dir), Path(out_root)
    if not in_dir.is_dir():
        raise UserError("La carpeta de entrada no existe.")
    if in_dir.resolve() == out_root.resolve() or out_root.resolve() in in_dir.resolve().parents and False:
        raise UserError("La carpeta de salida debe ser distinta de la de entrada.")
    with _LOCK:
        if watch_id in WATCHERS:
            raise UserError("Ya hay una carpeta vigilada con ese identificador.")
    state = {"procesados": [], "en_curso": None, "recipe": recipe["nombre"], "entrada": str(in_dir), "salida": str(out_root)}

    class H(FileSystemEventHandler):
        def on_created(self, event):
            p = Path(event.src_path)
            if event.is_directory or p.suffix.lower() not in INPUT_EXT:
                return
            threading.Thread(target=self._go, args=(p,), daemon=True).start()

        def _go(self, p):
            if not _wait_stable(p):
                return
            state["en_curso"] = p.name
            try:
                r = process_one(recipe, p, out_root)
                state["procesados"].append({"archivo": p.name, "estado": r["estado"], "motivo": r.get("motivo", ""), "hora": datetime.now().strftime("%H:%M:%S")})
            finally:
                state["en_curso"] = None

    obs = Observer()
    obs.schedule(H(), str(in_dir), recursive=False)
    obs.start()
    with _LOCK:
        WATCHERS[watch_id] = {"observer": obs, "state": state}
    return state


def stop_watch(watch_id: str) -> None:
    with _LOCK:
        w = WATCHERS.pop(watch_id, None)
    if not w:
        raise UserError("Esa carpeta vigilada no existe.")
    w["observer"].stop()
    w["observer"].join(timeout=5)


def watch_status() -> list[dict]:
    with _LOCK:
        return [{"id": k, **v["state"]} for k, v in WATCHERS.items()]
