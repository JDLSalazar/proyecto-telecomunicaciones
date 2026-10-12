#!/usr/bin/env bash
# =====================================================================
# deploy.sh - Copia los archivos del REPOSITORIO a /opt/prepago
#             (donde corre la API) y reinicia las 2 instancias.
# Uso:  bash ~/repo/api/deploy.sh
# =====================================================================

# Si cualquier comando falla, el script se detiene (evita dejar las cosas a medias).
set -e

# Carpeta raíz del repositorio. Este script vive en api/, así que la raíz es la carpeta de arriba.
REPO="$(cd "$(dirname "$0")/.." && pwd)"
echo "Desplegando desde: $REPO"

# --- Archivos de B (José): API y páginas ---
cp "$REPO/api/app.py"           /opt/prepago/app.py
cp "$REPO/api/requirements.txt" /opt/prepago/requirements.txt
cp "$REPO/portal/index.html"    /opt/prepago/static/index.html
cp "$REPO/portal/splash.html"   /opt/prepago/static/splash.html

# --- Archivos de C (Jhonatan): se copian SOLO si ya existen en el repositorio ---
# "if [ -f archivo ]" = "si el archivo existe".
if [ -f "$REPO/ocr/ocr_card.py" ]; then
  cp "$REPO/ocr/ocr_card.py" /opt/prepago/
  echo "  + ocr_card.py"
fi
if [ -f "$REPO/dashboard/metrics.py" ]; then
  cp "$REPO/dashboard/metrics.py" /opt/prepago/
  echo "  + metrics.py"
fi
if [ -f "$REPO/dashboard/dashboard.html" ]; then
  cp "$REPO/dashboard/dashboard.html" /opt/prepago/static/
  echo "  + dashboard.html"
fi

# --- Reiniciar las 2 instancias para que tomen el código nuevo ---
sudo systemctl restart prepago-api@5001 prepago-api@5002
sleep 2    # da 2 segundos para que arranquen

# --- Comprobar que responden ---
echo "Salud de las instancias:"
curl -s http://localhost:5001/health; echo
curl -s http://localhost:5002/health; echo
echo "Listo."