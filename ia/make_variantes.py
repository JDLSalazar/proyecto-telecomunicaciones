"""
make_variantes.py - Crea versiones "maltratadas" de una tarjeta de prueba que imitan
problemas de una foto real: torcida, borrosa, oscura, pequeña, con ruido, con reflejo
y dentro de una foto más grande (la tarjeta sobre una mesa).

NO reemplaza las fotos reales con el celular: es un complemento para medir el OCR.

Uso:  python make_variantes.py tarjeta.png carpeta_salida
Crea las imágenes y un archivo esperado.csv (archivo, condición, número esperado)
que luego usa medir_ocr.py.
"""
import csv                                         # escribir el archivo esperado.csv
import os                                          # crear carpetas y unir rutas
import random                                      # números al azar (para el ruido)
import sys
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

EXPECTED = "4242424242004242"   # número de la tarjeta base (cámbialo si usas otra)


def on_table(card):
    """Pone la tarjeta pequeña y un poco girada sobre un fondo gris-café, como si
    fuera una foto de la tarjeta sobre una mesa."""
    bg = Image.new("RGB", (2400, 1800), (120, 105, 90))
    small = card.resize((1000, 620)).rotate(4, expand=True, fillcolor=(120, 105, 90))
    bg.paste(small, (700, 600))
    return bg


def with_glare(card):
    """Dibuja una mancha blanca semitransparente: imita el reflejo de una lámpara."""
    img = card.copy().convert("RGBA")
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse((550, 180, 900, 420), fill=(255, 255, 255, 150))
    return Image.alpha_composite(img, layer).convert("RGB")


def with_noise(card, amount=40):
    """Agrega puntos de ruido al azar: imita una foto con poca luz (granulada)."""
    img = card.copy()
    px = img.load()
    random.seed(1)                                # siempre el mismo ruido (pruebas repetibles)
    for _ in range(img.width * img.height // 6):
        x, y = random.randrange(img.width), random.randrange(img.height)
        r, g, b = px[x, y]
        n = random.randint(-amount, amount)
        px[x, y] = (max(0, min(255, r + n)), max(0, min(255, g + n)), max(0, min(255, b + n)))
    return img


# Lista de condiciones: (nombre del archivo, descripción, función que transforma la tarjeta).
# "lambda c: ..." es una función pequeña sin nombre que recibe la tarjeta c.
CONDITIONS = [
    ("v01_original.png",   "Limpia (generada)",           lambda c: c),
    ("v02_rotada5.png",    "Torcida 5 grados",            lambda c: c.rotate(5, expand=True, fillcolor="white")),
    ("v03_rotada12.png",   "Torcida 12 grados",           lambda c: c.rotate(12, expand=True, fillcolor="white")),
    ("v04_borrosa.png",    "Desenfocada (leve)",          lambda c: c.filter(ImageFilter.GaussianBlur(2))),
    ("v05_muyborrosa.png", "Desenfocada (fuerte)",        lambda c: c.filter(ImageFilter.GaussianBlur(5))),
    ("v06_oscura.png",     "Poca luz",                    lambda c: ImageEnhance.Brightness(c).enhance(0.35)),
    ("v07_ruido.png",      "Poca luz con ruido",          lambda c: with_noise(ImageEnhance.Brightness(c).enhance(0.5))),
    ("v08_pequena.png",    "Muy pequeña (de lejos)",      lambda c: c.resize((330, 205))),
    ("v09_reflejo.png",    "Reflejo sobre el número",     with_glare),
    ("v10_mesa.jpg",       "Sobre una mesa (foto grande)", on_table),
    ("v11_jpeg_baja.jpg",  "JPEG de baja calidad",        lambda c: c),
]

if __name__ == "__main__":
    src, out_dir = sys.argv[1], sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)           # crea la carpeta si no existe
    card = Image.open(src).convert("RGB")
    rows = []
    for name, desc, fn in CONDITIONS:
        img = fn(card)
        path = os.path.join(out_dir, name)
        # La v11 se guarda con calidad JPEG 15 (muy comprimida); las demás .jpg con 85.
        if name.endswith(".jpg"):
            img.save(path, quality=15 if "baja" in name else 85)
        else:
            img.save(path)
        rows.append([name, desc, EXPECTED])
        print("creada", path)
    # esperado.csv: la "hoja de respuestas" que usará medir_ocr.py.
    with open(os.path.join(out_dir, "esperado.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["archivo", "condicion", "esperado"])
        w.writerows(rows)
    print("creado", os.path.join(out_dir, "esperado.csv"))