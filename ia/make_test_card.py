"""
make_test_card.py - Genera imágenes de tarjetas DE PRUEBA (números ficticios)
para probar el OCR. NUNCA uses una tarjeta real para probar.

Uso:
  python make_test_card.py                          -> tarjeta_prueba.png (4242424242004242, 12/29)
  python make_test_card.py NUMERO SALIDA.png        -> tarjeta con ese número
  python make_test_card.py NUMERO SALIDA.png 01/20  -> tarjeta con otro vencimiento
  python make_test_card.py --hoja                   -> hoja_tarjetas.png con las 5 tarjetas para imprimir
"""
import sys                                    # leer los argumentos que escribes en la terminal
from PIL import Image, ImageDraw, ImageFont   # Pillow: crear imágenes, dibujar y usar fuentes

# Las 5 tarjetas de prueba del proyecto: (número, vencimiento, resultado esperado en la API).
TEST_CARDS = [
    ("4242424242004242", "12/29", "APROBADA"),
    ("4242424242080002", "12/29", "RECHAZADA (DECLINED)"),
    ("4242424242089995", "12/29", "FONDOS INSUFICIENTES"),
    ("4242424242080119", "12/29", "TIMEOUT DE PASARELA"),
    ("4242424242004242", "01/20", "VENCIDA (CARD_EXPIRED)"),
]

def load_font(name, size):
    """Carga una fuente TrueType. Si no existe, DETIENE el programa con un mensaje claro
    (la guía original usaba una letra diminuta de respaldo y el OCR fallaba sin avisar)."""
    try:
        return ImageFont.truetype(name, size)
    except OSError:
        sys.exit(f"No se encontró la fuente {name}. Instálala con: sudo apt install -y fonts-dejavu-core")

def make_card(number, expiry="12/29"):
    """Dibuja UNA tarjeta de 1000 x 620 píxeles y devuelve la imagen (no la guarda)."""
    # Agrupa el número de 4 en 4, como en una tarjeta real: "4242 4242 4242 4242".
    grouped = " ".join(number[i:i + 4] for i in range(0, len(number), 4))
    img = Image.new("RGB", (1000, 620), (30, 60, 120))     # fondo azul oscuro
    d = ImageDraw.Draw(img)                                # "lápiz" para dibujar sobre la imagen
    big = load_font("DejaVuSansMono-Bold.ttf", 64)         # letra grande para el número
    small = load_font("DejaVuSansMono.ttf", 38)            # letra pequeña para el resto
    # d.text((x, y), texto, ...): x = distancia desde la izquierda, y = desde arriba (en píxeles).
    d.text((60, 120), "TARJETA DE PRUEBA", font=small, fill="white")
    d.text((60, 280), grouped, font=big, fill="white")
    d.text((60, 420), "VALID THRU " + expiry, font=small, fill="white")
    return img

def make_sheet(out="hoja_tarjetas.png"):
    """Crea una hoja para imprimir con las 5 tarjetas de prueba (2 columnas) y una etiqueta
    DEBAJO de cada una que dice qué resultado debe dar. La etiqueta va fuera de la tarjeta
    para no confundir al OCR."""
    # Hoja tamaño carta a 150 puntos por pulgada: 8.5 x 11 pulgadas = 1275 x 1650 píxeles.
    sheet = Image.new("RGB", (1275, 1650), "white")
    d = ImageDraw.Draw(sheet)
    label_font = load_font("DejaVuSans.ttf", 22)
    title_font = load_font("DejaVuSans-Bold.ttf", 30)
    d.text((60, 40), "Tarjetas de PRUEBA (ficticias) - Proyecto Internet Prepago", font=title_font, fill="black")
    # Cada tarjeta se reduce a la mitad: 500 x 310 px = unos 8.5 x 5.3 cm al imprimir.
    for i, (num, exp, result) in enumerate(TEST_CARDS):
        card = make_card(num, exp).resize((500, 310))
        col, row = i % 2, i // 2                         # posición en la cuadrícula (2 columnas)
        x, y = 80 + col * 590, 120 + row * 480
        sheet.paste(card, (x, y))                        # pega la tarjeta en la hoja
        d.text((x, y + 320), f"{num}  {exp}", font=label_font, fill="black")
        d.text((x, y + 350), f"Resultado esperado: {result}", font=label_font, fill="black")
    sheet.save(out)
    print("creada", out)

# ---------- Programa principal: decide qué hacer según los argumentos ----------
if __name__ == "__main__":
    # sys.argv es la lista de lo que escribiste: ["make_test_card.py", "NUMERO", "SALIDA.png", ...]
    if len(sys.argv) > 1 and sys.argv[1] == "--hoja":
        make_sheet(sys.argv[2] if len(sys.argv) > 2 else "hoja_tarjetas.png")
    else:
        number = sys.argv[1] if len(sys.argv) > 1 else "4242424242004242"
        out = sys.argv[2] if len(sys.argv) > 2 else "tarjeta_prueba.png"
        expiry = sys.argv[3] if len(sys.argv) > 3 else "12/29"
        make_card(number, expiry).save(out)
        print("creada", out)