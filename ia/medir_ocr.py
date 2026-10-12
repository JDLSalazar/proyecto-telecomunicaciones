"""
medir_ocr.py - Mide la tasa de acierto del OCR (la tabla que pide la prueba C2.2).

Uso:  python medir_ocr.py carpeta
La carpeta debe tener las imágenes y un archivo esperado.csv con las columnas:
    archivo,condicion,esperado
Ejemplo de una fila para una foto tuya:
    foto1.jpg,Celular de cerca con buena luz,4242424242004242

Muestra la tabla en pantalla y la guarda en carpeta/resultados.csv
(se abre con Excel o Google Sheets para pegarla en el informe).
"""
import csv
import os
import sys
import time

# Permite importar ocr_card.py, que está en la misma carpeta que este script.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ocr_card import read_card


def main(folder):
    with open(os.path.join(folder, "esperado.csv"), encoding="utf-8") as f:
        rows = list(csv.DictReader(f))     # cada fila es un diccionario: fila["archivo"], ...

    results, hits = [], 0
    print(f"{'archivo':22} {'condición':32} {'leído':18} {'venc.':6} {'s':>5}  ¿acertó?")
    for r in rows:
        with open(os.path.join(folder, r["archivo"]), "rb") as img:
            data = img.read()
        t = time.time()
        try:
            res = read_card(data)
        except Exception as e:                       # imagen dañada, etc.
            res = {"card_number": "", "expiry": "", "error": str(e)}
        secs = time.time() - t
        ok = res["card_number"] == r["esperado"]     # acierto = leyó EXACTAMENTE el número esperado
        hits += ok                                   # True cuenta como 1, False como 0
        leido = res["card_number"] or "(nada)"
        print(f"{r['archivo']:22} {r['condicion'][:32]:32} {leido:18} {res['expiry'] or '-':6} "
              f"{secs:5.2f}  {'SÍ' if ok else 'NO'}")
        results.append([r["archivo"], r["condicion"], r["esperado"], res["card_number"],
                        res["expiry"], f"{secs:.2f}", "sí" if ok else "no"])

    pct = 100 * hits / len(rows) if rows else 0
    print(f"\nAciertos: {hits} de {len(rows)}  ->  {pct:.0f} %")

    with open(os.path.join(folder, "resultados.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["archivo", "condicion", "esperado", "leido", "vencimiento", "segundos", "acerto"])
        w.writerows(results)
        w.writerow([])
        w.writerow(["TOTAL", "", "", "", "", "", f"{hits}/{len(rows)} ({pct:.0f} %)"])
    print("Tabla guardada en", os.path.join(folder, "resultados.csv"))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")