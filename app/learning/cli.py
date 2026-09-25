"""Comando `faverview-aprender`:  uv run faverview-aprender --ajustar | --entrenar | --resumen | --exportar | --importar"""
import argparse
import json
import sys
from pathlib import Path

from . import confusions, finetune, portability, store, tuning, vocab


def resumen() -> dict:
    st = store.state()
    ajustes = store.load_json("ajustes_ocr.json", {})
    return {
        "casos_revisados": st["casos_revisados"],
        "vocabulario": len(vocab.counts()),
        "confusiones": len(confusions.load()["pares"]),
        "ajustes_por_tipo": {t: {"cer_antes": a["cer_antes"], "cer_despues": a["cer_despues"], "lineas": a["lineas"]}
                             for t, a in ajustes.items()},
        "lineas_para_entrenar": finetune.count_lines(),
        "modelo": store.load_json("modelo_info.json", None),
        "modelo_activo": finetune.is_active(),
        "ab": store.load_json("ab_resultado.json", None),
        "huella": store.fingerprint(),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="faverview-aprender",
                                 description="OCR que aprende con los casos revisados (datos en datos_locales/aprendizaje)")
    ap.add_argument("--resumen", action="store_true", help="muestra el estado del aprendizaje")
    ap.add_argument("--ajustar", action="store_true", help="nivel 3: auto-ajusta el preprocesado por tipo de imagen")
    ap.add_argument("--entrenar", action="store_true", help="nivel 4: re-entrena el modelo spa (≥300 líneas) y hace la prueba A/B")
    ap.add_argument("--iteraciones", type=int, default=800)
    ap.add_argument("--original", action="store_true", help="vuelve al modelo original de Tesseract")
    ap.add_argument("--exportar", metavar="ARCHIVO.zip")
    ap.add_argument("--con-recortes", action="store_true", help="incluir recortes de clientes en la exportación (privado)")
    ap.add_argument("--importar", metavar="ARCHIVO.zip")
    a = ap.parse_args(argv)

    did = False
    if a.original:
        finetune.activate(False)
        print("Se volvió al modelo original de Tesseract.")
        did = True
    if a.ajustar:
        res = tuning.autotune(log=print)
        print(json.dumps(res, ensure_ascii=False, indent=1))
        did = True
    if a.entrenar:
        info = finetune.train(a.iteraciones, log=print)
        print(info["mensaje"])
        if info.get("ok"):
            print(finetune.ab_test(log=print)["mensaje"])
        did = True
    if a.exportar:
        Path(a.exportar).write_bytes(portability.export_zip(a.con_recortes))
        print("Aprendizaje exportado en", a.exportar)
        did = True
    if a.importar:
        print("Importado:", portability.import_zip(Path(a.importar).read_bytes()))
        did = True
    if a.resumen or not did:
        print(json.dumps(resumen(), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
