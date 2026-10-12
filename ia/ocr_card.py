"""
ocr_card.py - Lectura de tarjeta por OCR (componente mínimo de IA del proyecto).

Recibe la FOTO de una tarjeta (en bytes), extrae el número (validado con Luhn) y el
vencimiento MM/AA. La API (app.py) lo usa en POST /api/scan-card.

PRIVACIDAD: la imagen se procesa solo en memoria; NO se guarda en disco y el número
NO se escribe en ningún log.

Contrato con app.py:
    read_card(image_bytes) -> {"card_number": "4242424242004242" o "",
                               "expiry": "12/29" o "",
                               "valid_luhn": True/False}
"""
import io                                   # tratar los bytes de la foto como si fueran un archivo
import re                                   # expresiones regulares: buscar patrones en el texto
from PIL import Image, ImageOps             # Pillow: abrir y transformar imágenes
import pytesseract                          # puente entre Python y el programa Tesseract

# Configuración de Tesseract:
#   --psm 6  = "trata la imagen como un bloque de texto uniforme"
#   whitelist = solo puede "ver" dígitos, la barra "/" y espacios. Así no confunde
#               letras con números (por ejemplo la O con el 0) y lee más rápido.
TESS_CONFIG = "--psm 6 -c tessedit_char_whitelist=0123456789/ "


def luhn_ok(number):
    """True si el número pasa el algoritmo de Luhn (misma regla que usa app.py)."""
    d = [int(c) for c in number if c.isdigit()]
    if len(d) < 13 or len(d) > 19:            # largo de una tarjeta real
        return False
    s = 0
    for i, x in enumerate(reversed(d)):       # de derecha a izquierda
        if i % 2:                             # uno sí y uno no
            x *= 2
            if x > 9:
                x -= 9
        s += x
    return s % 10 == 0                        # válido si es múltiplo de 10


def parse_card_text(text):
    """Busca en el texto que leyó el OCR un número de tarjeta válido y un vencimiento.
    Devuelve (numero, vencimiento); cada uno puede ser "" si no se encontró."""
    number = ""
    # 1) Secuencias de 13 a 19 dígitos que pueden tener un espacio o guion entre ellos
    #    ("4242 4242 4242 4242"). Nos quedamos con la PRIMERA que pase Luhn:
    #    un número mal leído casi nunca cumple Luhn, así se descartan errores del OCR.
    for m in re.finditer(r"(?:\d[ \-]?){13,19}", text):
        digits = re.sub(r"\D", "", m.group())          # quita espacios y guiones
        if luhn_ok(digits):
            number = digits
            break
    # 2) Respaldo: une TODOS los dígitos de cada renglón (por si el OCR metió espacios dobles).
    if not number:
        for line in text.splitlines():
            digits = re.sub(r"\D", "", line)
            if luhn_ok(digits):
                number = digits
                break
    # 3) Vencimiento: mes 01-12, una "/" y dos dígitos de año (ej. "12/29").
    exp = re.search(r"(?<!\d)(0[1-9]|1[0-2])\s*/\s*(\d{2})(?!\d)", text)
    expiry = f"{exp.group(1)}/{exp.group(2)}" if exp else ""
    return number, expiry


def prepare(image_bytes):
    """Prepara la foto para el OCR y devuelve una imagen en escala de grises."""
    img = Image.open(io.BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img)        # corrige la rotación que guarda el celular
    img = img.convert("L")                    # escala de grises ("L" = solo brillo)
    # Tamaño: las fotos de celular son enormes (unos 4000 px de ancho) y el OCR tardaría
    # mucho; las muy pequeñas se leen mal. Se lleva el ancho a un rango de 1000 a 1600 px.
    if img.width > 1600:
        k = 1600 / img.width
        img = img.resize((1600, int(img.height * k)))
    elif img.width < 1000:
        k = 1000 / img.width
        img = img.resize((1000, int(img.height * k)))
    return ImageOps.autocontrast(img)         # estira el contraste: oscuros más oscuros, claros más claros


def variants(gray):
    """Genera versiones distintas de la imagen para hacer varios intentos de lectura.
    Se prueban en orden y se detiene en la primera que dé un número válido."""
    yield gray                                     # 1) tal cual (gris con contraste)
    yield ImageOps.invert(gray)                    # 2) invertida: Tesseract lee mejor
                                                   #    letra OSCURA sobre fondo CLARO,
                                                   #    y las tarjetas suelen ser al revés
    # 3) Blanco y negro puro: cada píxel se vuelve negro o blanco según si supera
    #    el brillo promedio. Ayuda con fondos con dibujos o sombras.
    avg = sum(gray.getdata()) / (gray.width * gray.height)
    bw = gray.point(lambda p: 255 if p > avg else 0)
    yield ImageOps.invert(bw)


def read_card(image_bytes):
    """Lee el número y el vencimiento de la foto de una tarjeta.
    Si la imagen no se puede abrir, lanza una excepción (app.py responde OCR_FAILED)."""
    gray = prepare(image_bytes)
    best_expiry = ""
    for img in variants(gray):
        # timeout=10: si Tesseract tarda más de 10 s se corta, para no colgar la API.
        text = pytesseract.image_to_string(img, config=TESS_CONFIG, timeout=10)
        number, expiry = parse_card_text(text)
        best_expiry = best_expiry or expiry       # guarda el primer vencimiento que encuentre
        if number:                                # ¡número válido! no hace falta seguir intentando
            return {"card_number": number, "expiry": expiry or best_expiry, "valid_luhn": True}
    # Ningún intento encontró un número que pase Luhn.
    return {"card_number": "", "expiry": best_expiry, "valid_luhn": False}


# Prueba rápida desde la terminal:  python ocr_card.py foto.jpg
if __name__ == "__main__":
    import sys, time
    t = time.time()
    with open(sys.argv[1], "rb") as f:
        print(read_card(f.read()))
    print(f"tiempo: {time.time() - t:.2f} s")