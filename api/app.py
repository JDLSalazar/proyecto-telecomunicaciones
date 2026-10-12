# =====================================================================
#  app.py - API del sistema "Internet Prepago"  (Integrante B: José Díaz)
#  Parte 1: configuración, /health, /api/plans y /api/register
# =====================================================================

# ---------- 1. LIBRERÍAS QUE USAMOS ----------
import os                  # leer variables de entorno (como DB_PASS de /etc/prepago.env)
import re                  # "expresiones regulares": revisar si un texto tiene cierto formato
import time                # pausas (simular la demora del banco) -> se usa en la Parte 2
import uuid                # generar códigos únicos de referencia de pago -> Parte 2
from datetime import datetime, timedelta   # fechas y sumas de tiempo -> Parte 2

import pymysql                              # conectarse a MariaDB
from flask import Flask, request, jsonify   # Flask: crear la API; request: datos que llegan;
                                            # jsonify: convertir respuestas a JSON
from passlib.hash import sha512_crypt       # crear el hash SHA-512 de las contraseñas

# ---------- 2. CREAR LA APLICACIÓN ----------
# "static" es la carpeta donde estarán las páginas web (la tienda, el dashboard).
app = Flask(__name__, static_folder="static")

# Tamaño máximo de lo que se puede enviar a la API: 6 MB (por las fotos de tarjetas del OCR).
app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024
app.json.ensure_ascii = False
app.json.sort_keys = False
# Nombre de esta instancia. Tendremos 2 copias de la API (puertos 5001 y 5002);
# cada una dirá su nombre en /health para saber cuál respondió. Si no se define, vale "dev".
INSTANCE = os.environ.get("INSTANCE", "dev")

# ---------- 3. PLANES A LA VENTA ----------
# Un "diccionario": cada clave ("1h", "1d", "7d") tiene su nombre, precio en quetzales
# y duración en segundos (3600 s = 1 hora, 86400 s = 1 día, 604800 s = 7 días).
PLANS = {
    "1h": {"name": "1 hora", "price": 5.00,  "seconds": 3600},
    "1d": {"name": "1 día",  "price": 15.00, "seconds": 86400},
    "7d": {"name": "7 días", "price": 80.00, "seconds": 604800},
}

# ---------- 4. FUNCIONES DE APOYO ----------
def db():
    """Abre una conexión nueva a la base de datos 'radius' y la devuelve."""
    return pymysql.connect(
        host="localhost",                    # MariaDB está en esta misma VM
        user="radius",                       # el usuario creado en el Paso 2.2
        password=os.environ["DB_PASS"],      # la contraseña se lee de /etc/prepago.env
        database="radius",
        cursorclass=pymysql.cursors.DictCursor,  # las filas llegan como diccionarios:
                                                 # fila["username"] en vez de fila[0]
        autocommit=False)                    # los cambios solo se guardan al hacer commit()
                                             # (si algo falla a medio camino, no queda nada a medias)

def err(msg, code, status):
    """Arma una respuesta de ERROR con el mismo formato siempre:
       msg    -> mensaje para el cliente (en español)
       code   -> código corto para programas (ej. "USER_EXISTS")
       status -> código HTTP (ej. 409)"""
    return jsonify({"ok": False, "error": code, "message": msg}), status

# ---------- 5. ENDPOINTS (RUTAS DE LA API) ----------

@app.get("/health")
def health():
    """Chequeo de salud. HAProxy (en pfSense) llamará aquí cada pocos segundos.
       Si la base de datos responde -> 200 "ok"; si no -> 503 y HAProxy deja
       de mandarle clientes a esta instancia."""
    try:
        c = db()                              # intenta conectarse
        c.cursor().execute("SELECT 1")        # la consulta más simple posible
        c.close()
        return jsonify({"status": "ok", "instance": INSTANCE})
    except Exception:                          # cualquier fallo de conexión cae aquí
        return jsonify({"status": "db_error", "instance": INSTANCE}), 503

@app.get("/api/plans")
def plans():
    """Devuelve la lista de planes para que la tienda los muestre."""
    return jsonify(PLANS)

@app.post("/api/register")
def register():
    """Registra un cliente nuevo. Recibe un JSON como:
       {"username": "cliente1", "email": "a@b.com", "phone": "5555-5555", "password": "Clave12345"}"""
    # Lee el JSON que envió la tienda. Si llega vacío o mal formado, usa {} para no fallar.
    d = request.get_json(silent=True) or {}

    # Toma cada dato. .strip() quita espacios al inicio/final; .lower() pasa a minúsculas
    # el usuario (así "Cliente1" y "cliente1" son el mismo).
    u = d.get("username", "").strip().lower()
    e = d.get("email", "").strip()
    t = d.get("phone", "").strip()
    p = d.get("password", "")

    # --- Validaciones: si algo está mal, respondemos 422 con el motivo ---
    # Usuario: solo a-z, 0-9 y _, de 4 a 20 caracteres.
    if not re.fullmatch(r"[a-z0-9_]{4,20}", u):
        return err("Usuario: 4-20 caracteres (a-z, 0-9, _).", "BAD_USERNAME", 422)
    # Correo: algo@algo.algo y máximo 120 caracteres (el tamaño de la columna).
    if len(e) > 120 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", e):
        return err("Correo inválido.", "BAD_EMAIL", 422)
    # Teléfono: opcional; si viene, solo dígitos, espacios, + y -, máximo 20.
    if t and not re.fullmatch(r"[0-9 +\-]{1,20}", t):
        return err("Teléfono inválido.", "BAD_PHONE", 422)
    # Contraseña: entre 8 y 64 caracteres.
    if not 8 <= len(p) <= 64:
        return err("La contraseña debe tener entre 8 y 64 caracteres.", "WEAK_PASSWORD", 422)

    # --- Guardar en la base de datos ---
    c = db()
    try:
        cur = c.cursor()
        # Los %s son "espacios" que pymysql llena de forma SEGURA con los valores.
        # Esto evita la "inyección SQL" (que alguien meta comandos SQL en un campo).
        # La contraseña se guarda como HASH, nunca en texto plano.
        cur.execute(
            "INSERT INTO app_users (username, email, phone, password_hash) VALUES (%s, %s, %s, %s)",
            (u, e, t, sha512_crypt.hash(p)))
        c.commit()                             # confirma y guarda el cambio
        # Devolvemos el usuario ya normalizado (en minúsculas) para que la tienda lo use.
        return jsonify({"ok": True, "username": u})
    except pymysql.err.IntegrityError:         # la columna username es UNIQUE: si ya existe, cae aquí
        return err("Ese usuario ya existe.", "USER_EXISTS", 409)
    finally:
        c.close()                              # "finally" se ejecuta SIEMPRE: cerramos la conexión

@app.get("/")
def index():
    """Página principal: entrega la tienda (static/index.html). La crearemos en la Etapa 6;
       mientras no exista, esta ruta responde 404 y es normal."""
    return app.send_static_file("index.html")

# =====================================================================
#  PARTE 2: validación de tarjeta, pasarela simulada, activación y /api/pay
# =====================================================================

def luhn_ok(number):
    """Devuelve True si el número de tarjeta pasa el algoritmo de Luhn."""
    # Convierte el texto en una lista de dígitos: "4242" -> [4, 2, 4, 2]
    d = [int(c) for c in number if c.isdigit()]
    # Las tarjetas reales tienen entre 13 y 19 dígitos.
    if len(d) < 13 or len(d) > 19:
        return False
    s = 0
    # reversed(d) recorre los dígitos de DERECHA a IZQUIERDA.
    # enumerate da también la posición i (0, 1, 2, ...).
    for i, x in enumerate(reversed(d)):
        if i % 2:              # posiciones impares (2.º, 4.º, 6.º... contando desde el final)
            x *= 2             # se duplica el dígito
            if x > 9:
                x -= 9         # si pasa de 9, se le resta 9
        s += x                 # se va sumando todo
    return s % 10 == 0         # válido si la suma es múltiplo de 10

def expiry_ok(exp):
    """Revisa el vencimiento en formato MM/AA. La tarjeta vale hasta el FINAL de ese mes."""
    # Expresión regular: mes 01-12, una "/" (con espacios opcionales) y 2 dígitos de año.
    m = re.fullmatch(r"(0[1-9]|1[0-2])\s*/\s*(\d{2})", (exp or "").strip())
    if not m:
        return False                               # formato incorrecto
    month, year = int(m.group(1)), 2000 + int(m.group(2))   # "12/29" -> mes 12, año 2029
    now = datetime.now()
    # Compara (año, mes) como pares. Válido si NO está en el pasado y no está
    # absurdamente lejos en el futuro (máximo 20 años).
    return (now.year, now.month) <= (year, month) <= (now.year + 20, 12)

def mock_gateway(card, amount):
    """Pasarela de pago SIMULADA (no hay banco real). Decide según los ÚLTIMOS 4 dígitos:
         0002 -> rechazada | 9995 -> fondos insuficientes | 0119 -> timeout | otro -> aprobada
       Devuelve 3 valores: (¿aprobado?, código, código HTTP)."""
    time.sleep(0.8)                      # simula que el "banco" tarda en responder
    last4 = card[-4:]                    # [-4:] = los últimos 4 caracteres
    if last4 == "0002": return False, "DECLINED", 402
    if last4 == "9995": return False, "INSUFFICIENT_FUNDS", 402
    if last4 == "0119": return False, "GATEWAY_TIMEOUT", 504
    return True, "APPROVED", 200

def activate_user(cur, username, seconds):
    """Crea o renueva la cuenta RADIUS del cliente en la tabla radcheck.
       Escribe 2 filas: Crypt-Password (la clave con hash) y Expiration (vencimiento).
       Si el cliente aún tenía tiempo, el nuevo plan se SUMA al que le quedaba."""
    # 1) Trae el hash de la contraseña que se guardó al registrarse.
    cur.execute("SELECT password_hash FROM app_users WHERE username=%s", (username,))
    ph = cur.fetchone()["password_hash"]

    # 2) ¿Desde cuándo empieza a contar el plan? Por defecto, desde AHORA.
    base = datetime.now()
    cur.execute("SELECT value FROM radcheck WHERE username=%s AND attribute='Expiration'", (username,))
    row = cur.fetchone()
    if row:                              # ya tenía un plan: es una RENOVACIÓN
        try:
            # fromtimestamp convierte los segundos guardados en una fecha.
            # max() elige la fecha más lejana: si el plan anterior aún no vence,
            # el nuevo empieza cuando termine el anterior (no se pierde tiempo pagado).
            base = max(base, datetime.fromtimestamp(int(row["value"])))
        except ValueError:
            pass                         # si el valor guardado está dañado, se ignora

    # 3) Nueva fecha de vencimiento = base + duración del plan.
    exp = base + timedelta(seconds=seconds)

    # 4) Borra las filas viejas del usuario y escribe las 2 nuevas.
    cur.execute("DELETE FROM radcheck WHERE username=%s", (username,))
    cur.executemany(                     # executemany = el mismo INSERT para varias filas
        "INSERT INTO radcheck (username, attribute, op, value) VALUES (%s, %s, %s, %s)",
        [(username, "Crypt-Password", ":=", ph),
         # timestamp() = segundos desde 1970 (el formato que probaste en el Paso 3.5).
         (username, "Expiration", ":=", str(int(exp.timestamp())))])
    return exp

@app.post("/api/pay")
def pay():
    """Procesa un pago. Recibe un JSON como:
       {"username":"cliente1","plan":"1h","card_number":"4242424242004242","expiry":"12/29","cvv":"123"}"""
    d = request.get_json(silent=True) or {}
    u = str(d.get("username", "")).strip().lower()
    plan_key = str(d.get("plan", ""))
    plan = PLANS.get(plan_key)           # None si el plan no existe
    # re.sub(r"\D", "", ...) BORRA todo lo que no sea dígito (espacios, guiones):
    # "4242 4242-..." -> "42424242..."
    card = re.sub(r"\D", "", str(d.get("card_number", "")))

    # --- Validaciones (antes de tocar la base de datos) ---
    if not plan:
        return err("Plan inválido.", "BAD_PLAN", 422)
    if not luhn_ok(card):
        return err("Número de tarjeta inválido.", "CARD_INVALID", 422)
    if not expiry_ok(d.get("expiry", "")):
        return err("Tarjeta vencida o fecha inválida (usa MM/AA).", "CARD_EXPIRED", 422)
    if not re.fullmatch(r"\d{3,4}", str(d.get("cvv", ""))):
        return err("CVV inválido.", "CVV_INVALID", 422)

    c = db()
    try:
        cur = c.cursor()
        # ¿El usuario existe?
        cur.execute("SELECT 1 FROM app_users WHERE username=%s", (u,))
        if not cur.fetchone():
            return err("Usuario no registrado.", "NO_USER", 404)

        # Se "cobra" en la pasarela simulada.
        ok, code, status = mock_gateway(card, plan["price"])
        ref = uuid.uuid4().hex[:12]      # referencia única de 12 caracteres (como un nº de recibo)

        # Se registra el intento (aprobado o fallido) en app_payments.
        # SEGURIDAD: NUNCA se guarda el número completo ni el CVV, solo los últimos 4 dígitos.
        cur.execute(
            "INSERT INTO app_payments (username, plan, amount, status, card_last4, reference, error_code) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (u, plan_key, plan["price"], "approved" if ok else "failed",
             card[-4:], ref, None if ok else code))

        if not ok:                       # pago rechazado: se guarda el intento y se avisa
            c.commit()
            return err("Pago no aprobado: " + code, code, status)

        # Pago aprobado: se activa la cuenta en RADIUS.
        exp = activate_user(cur, u, plan["seconds"])
        # UN SOLO commit guarda a la vez el pago y la cuenta RADIUS: o se guarda todo
        # o nada (si algo falla antes, no queda un pago aprobado sin cuenta activa).
        c.commit()
        return jsonify({"ok": True, "reference": ref, "plan": plan["name"],
                        "expires_at": exp.strftime("%Y-%m-%d %H:%M:%S")})
    finally:
        c.close()

# =====================================================================
#  PARTE 3: módulos de Jhonatan (OCR y dashboard) y estadísticas
# =====================================================================

# ---------- Cargar los módulos de Jhonatan SI existen ----------
# "try / except ImportError" = "intenta importar; si el archivo no está, no te caigas".
# Si no están, la variable queda en None y esa función se desactiva sola.
try:
    from ocr_card import read_card        # ocr_card.py: lee número y vencimiento de una foto
except ImportError:
    read_card = None
try:
    import metrics                        # metrics.py: el dashboard simple
except ImportError:
    metrics = None

@app.post("/api/scan-card")
def scan_card():
    """Recibe la FOTO de la tarjeta, la lee con OCR y devuelve número y vencimiento.
       SEGURIDAD: la imagen NO se guarda en disco y el número NO se escribe en los logs."""
    # Si el módulo de Jhonatan no está instalado -> 503 (servicio no disponible).
    if read_card is None:
        return err("La lectura de tarjeta no está instalada en este servidor.", "OCR_UNAVAILABLE", 503)

    # La foto llega como "archivo" en un formulario (no como JSON), en el campo "image".
    f = request.files.get("image")
    if not f:
        return err("Envía una imagen de la tarjeta.", "NO_IMAGE", 422)

    try:
        # f.read() obtiene los bytes de la imagen EN MEMORIA y se los pasa al OCR.
        res = read_card(f.read())
    except Exception:                     # si el OCR falla por cualquier motivo
        return err("No se pudo leer la imagen.", "OCR_FAILED", 422)

    # El OCR devuelve un diccionario; si no encontró un número válido, avisamos.
    if not res.get("card_number"):
        return err("No se detectó un número de tarjeta válido. Prueba con más luz o escríbelo.",
                   "NO_CARD_FOUND", 422)

    # "**res" copia todo lo que devolvió el OCR (card_number, expiry...) dentro de la respuesta.
    return jsonify({"ok": True, **res})

@app.get("/api/stats")
def stats():
    """Estadísticas simples del negocio: total de usuarios, pagos aprobados y fallidos."""
    c = db()
    try:
        cur = c.cursor()
        # COUNT(*) cuenta filas. "n" es el nombre que le damos al resultado.
        cur.execute("SELECT COUNT(*) n FROM app_users")
        users = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) n FROM app_payments WHERE status='approved'")
        ok = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) n FROM app_payments WHERE status='failed'")
        bad = cur.fetchone()["n"]
        return jsonify({"users_total": users, "payments_ok": ok, "payments_failed": bad})
    finally:
        c.close()

# ---------- Rutas del dashboard (/dashboard y /api/metrics) ----------
# Si metrics.py existe, él mismo agrega sus rutas a la app y usa nuestra función db().
if metrics is not None:
    metrics.register(app, db)
