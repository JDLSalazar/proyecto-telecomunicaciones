"""
metrics.py - Dashboard simple (sin IA): métricas en vivo de disponibilidad, latencia,
ancho de banda, uptime, servicios y negocio.

app.py lo carga si existe y llama a  register(app, db), que agrega 2 rutas:
    GET /dashboard?key=CLAVE    -> la página (static/dashboard.html)
    GET /api/metrics?key=CLAVE  -> los datos en JSON (la página los pide cada 5 s)
Sin la clave correcta (DASH_TOKEN de /etc/prepago.env) ambas responden 403.
"""
import hmac                                   # comparar la clave de forma segura
import os                                     # leer variables de entorno
import re                                     # buscar patrones en el texto de ping y SNMP
import subprocess                             # ejecutar programas del sistema (ping, snmpget...)
import time
import urllib.request                         # hacer peticiones HTTP a /health
from concurrent.futures import ThreadPoolExecutor   # hacer varias mediciones A LA VEZ
from flask import jsonify, request

# ---------- Configuración (se lee de /etc/prepago.env) ----------
INSTANCES = {"5001": "http://127.0.0.1:5001/health",
             "5002": "http://127.0.0.1:5002/health"}
PFSENSE_IP = os.environ.get("PFSENSE_IP", "10.30.0.1")             # pfSense por IPv4
PFSENSE_IP6 = os.environ.get("PFSENSE_IP6", "fd00:0:0:30::1")      # pfSense por IPv6 (Dual Stack)
INTERNET_IP = "8.8.8.8"                                            # un servidor de internet conocido
SNMP_COMMUNITY = os.environ.get("SNMP_COMMUNITY", "")             # vacío = SNMP desactivado
SNMP_IFACE = os.environ.get("SNMP_IFACE", "em0")                  # interfaz de pfSense a medir
NET_IFACE = os.environ.get("NET_IFACE", "vlan30")                 # interfaz de esta VM a medir
DASH_TOKEN = os.environ.get("DASH_TOKEN", "")
CACHE_SECONDS = 3            # si varias pantallas piden métricas a la vez, se reutiliza la última medición
_if_index = {}               # memoria: nombre de interfaz de pfSense -> número SNMP
_cache = {"ts": 0, "data": None}


# =====================================================================
#  1. Funciones que LEEN o INTERPRETAN datos (separadas para poder probarlas)
# =====================================================================
def parse_ping(output):
    """Saca los milisegundos del texto de ping: '... time=0.42 ms' -> 0.42 (None si no respondió)."""
    m = re.search(r"time[=<]([\d.]+)\s*ms", output)
    return float(m.group(1)) if m else None


def ping_ms(host, ipv6=False):
    """Hace UN ping (espera máximo 1 s) y devuelve los ms, o None si no hubo respuesta."""
    cmd = ["ping", "-6" if ipv6 else "-4", "-c", "1", "-W", "1", host]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        return parse_ping(r.stdout)
    except Exception:
        return None


def parse_proc_net_dev(text, iface):
    """Lee el archivo /proc/net/dev de Linux, que tiene los bytes recibidos (rx) y
    enviados (tx) por cada interfaz desde que encendió la VM.
    Devuelve (nombre_usado, rx, tx). Si la interfaz pedida no existe, suma todas menos "lo"."""
    rx = tx = 0
    found = False
    for line in text.splitlines()[2:]:          # las 2 primeras líneas son encabezados
        if ":" not in line:
            continue
        name, data = line.split(":", 1)
        name, f = name.strip(), data.split()
        if len(f) < 9:
            continue
        if name == iface:                       # f[0] = bytes recibidos, f[8] = bytes enviados
            return iface, int(f[0]), int(f[8])
        if name != "lo":                        # "lo" es la interfaz interna (127.0.0.1): no cuenta
            rx += int(f[0]); tx += int(f[8]); found = True
    return ("todas", rx, tx) if found else (iface, None, None)


def system_uptime():
    """Segundos que lleva encendida la VM (primer número de /proc/uptime).
    Es el MISMO valor para las 2 instancias, aunque HAProxy alterne entre ellas."""
    try:
        with open("/proc/uptime") as f:
            return int(float(f.read().split()[0]))
    except (OSError, ValueError):
        return None


def service_active(name):
    """True si el servicio de systemd está corriendo ("systemctl is-active" responde "active")."""
    try:
        r = subprocess.run(["systemctl", "is-active", name], capture_output=True, text=True, timeout=3)
        return r.stdout.strip() == "active"
    except Exception:
        return None


def check_instance(url):
    """Llama a /health de una instancia y mide cuánto tarda. UP solo si responde 200."""
    t = time.time()
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return {"up": r.status == 200, "ms": round((time.time() - t) * 1000, 1)}
    except Exception:                           # no responde, 503, etc.
        return {"up": False, "ms": None}


# ---------- SNMP (opcional: solo si Josué activa SNMP en pfSense) ----------
def parse_snmp_walk_names(text):
    """'.1.3.6.1.2.1.31.1.1.1.1.5 = STRING: em0' -> {'em0': 5}  (nombre -> número de interfaz)"""
    res = {}
    for m in re.finditer(r"\.(\d+) = STRING: \"?([^\"\s]+)\"?", text):
        res[m.group(2)] = int(m.group(1))
    return res


def parse_snmp_value(text):
    """Saca el número de una respuesta de snmpget (contador, entero o tiempo)."""
    m = re.search(r"= (?:Counter64|Counter32|INTEGER|Gauge32): (\d+)", text)
    if m:
        return int(m.group(1))
    m = re.search(r"Timeticks: \((\d+)\)", text)       # Timeticks = centésimas de segundo
    return int(m.group(1)) if m else None


def _snmp(cmd, oid):
    return subprocess.run([cmd, "-v2c", "-c", SNMP_COMMUNITY, "-On", PFSENSE_IP, oid],
                          capture_output=True, text=True, timeout=4).stdout


def pfsense_snmp():
    """Uptime y bytes de la interfaz de pfSense por SNMP. None si SNMP está apagado o falla.
    OIDs (las "direcciones" de cada dato en SNMP):
      1.3.6.1.2.1.1.3.0            sysUpTime   (tiempo encendido)
      1.3.6.1.2.1.31.1.1.1.1.N     ifName      (nombre de la interfaz N)
      1.3.6.1.2.1.31.1.1.1.6.N     ifHCInOctets  (bytes recibidos, contador de 64 bits)
      1.3.6.1.2.1.31.1.1.1.10.N    ifHCOutOctets (bytes enviados)"""
    if not SNMP_COMMUNITY:
        return None
    try:
        if SNMP_IFACE not in _if_index:
            _if_index.update(parse_snmp_walk_names(_snmp("snmpwalk", "1.3.6.1.2.1.31.1.1.1.1")))
        idx = _if_index[SNMP_IFACE]
        up = parse_snmp_value(_snmp("snmpget", "1.3.6.1.2.1.1.3.0"))
        rx = parse_snmp_value(_snmp("snmpget", f"1.3.6.1.2.1.31.1.1.1.6.{idx}"))
        tx = parse_snmp_value(_snmp("snmpget", f"1.3.6.1.2.1.31.1.1.1.10.{idx}"))
        if None in (up, rx, tx):
            return None
        return {"uptime_s": up / 100, "iface": SNMP_IFACE, "in_octets": rx, "out_octets": tx}
    except Exception:
        return None


def business_stats(db):
    """Datos del negocio desde la base de datos. None si la base no responde."""
    try:
        c = db()
        try:
            cur = c.cursor()
            def one(sql):                       # ejecuta una consulta y devuelve el número "n"
                cur.execute(sql)
                return cur.fetchone()["n"]
            return {
                "users_total": one("SELECT COUNT(*) n FROM app_users"),
                "payments_ok": one("SELECT COUNT(*) n FROM app_payments WHERE status='approved'"),
                "payments_failed": one("SELECT COUNT(*) n FROM app_payments WHERE status='failed'"),
                # Ingresos simulados: suma de los pagos aprobados (COALESCE da 0 si no hay ninguno).
                "revenue": float(one("SELECT COALESCE(SUM(amount),0) n FROM app_payments WHERE status='approved'")),
                # Planes vigentes: cuentas RADIUS cuyo vencimiento todavía no llega.
                "active_plans": one("SELECT COUNT(*) n FROM radcheck WHERE attribute='Expiration' "
                                    "AND CAST(value AS UNSIGNED) > UNIX_TIMESTAMP()"),
            }
        finally:
            c.close()
    except Exception:
        return None


# =====================================================================
#  2. Juntar todo en una sola "foto" de métricas
# =====================================================================
def collect(db):
    """Toma todas las mediciones. Las lentas (pings, /health, SNMP, BD) se hacen EN PARALELO
    con hilos (threads), así la respuesta tarda ~1 s en lugar de sumar el tiempo de cada una."""
    with ThreadPoolExecutor(max_workers=8) as ex:
        # ex.submit(funcion, argumentos) la pone a correr y devuelve un "futuro" (resultado pendiente).
        f_inst = {p: ex.submit(check_instance, u) for p, u in INSTANCES.items()}
        f_gw = ex.submit(ping_ms, PFSENSE_IP)
        f_gw6 = ex.submit(ping_ms, PFSENSE_IP6, True)
        f_net = ex.submit(ping_ms, INTERNET_IP)
        f_snmp = ex.submit(pfsense_snmp)
        f_app = ex.submit(business_stats, db)
        f_rad = ex.submit(service_active, "freeradius")
        f_maria = ex.submit(service_active, "mariadb")
        try:
            with open("/proc/net/dev") as f:
                iface, rx, tx = parse_proc_net_dev(f.read(), NET_IFACE)
        except OSError:
            iface, rx, tx = NET_IFACE, None, None
        # .result() espera a que cada medición termine y devuelve su valor.
        return {
            "ok": True,
            "ts": time.time(),                                   # momento de la medición
            "instance": os.environ.get("INSTANCE", "dev"),       # qué instancia respondió
            "backend_uptime_s": system_uptime(),
            "instances": {p: f.result() for p, f in f_inst.items()},
            "services": {"freeradius": f_rad.result(), "mariadb": f_maria.result()},
            "latency": {"gateway_ms": f_gw.result(), "gateway6_ms": f_gw6.result(),
                        "internet_ms": f_net.result()},
            "backend_net": {"iface": iface, "rx_bytes": rx, "tx_bytes": tx},
            "pfsense": f_snmp.result(),
            "app": f_app.result(),
        }


def _auth_ok():
    """True si la clave ?key= coincide con DASH_TOKEN. compare_digest tarda lo mismo
    acierte o falle, así nadie puede adivinar la clave midiendo tiempos de respuesta."""
    key = request.args.get("key", "")
    return bool(DASH_TOKEN) and hmac.compare_digest(key.encode(), DASH_TOKEN.encode())


# =====================================================================
#  3. Rutas que se agregan a la app de Flask
# =====================================================================
def register(app, db):
    @app.get("/dashboard")
    def dashboard():
        if not _auth_ok():
            return "Acceso denegado (falta ?key= o DASH_TOKEN sin configurar).", 403
        resp = app.send_static_file("dashboard.html")      # igual que la tienda en app.py
        resp.headers["Cache-Control"] = "no-store"         # que el navegador no la guarde
        return resp

    @app.get("/api/metrics")
    def metrics():
        if not _auth_ok():
            return jsonify({"ok": False, "error": "FORBIDDEN"}), 403
        # Si la última medición tiene menos de 3 s, se reutiliza (varias pantallas abiertas).
        if time.time() - _cache["ts"] > CACHE_SECONDS or _cache["data"] is None:
            _cache["data"] = collect(db)
            _cache["ts"] = time.time()
        return jsonify(_cache["data"])