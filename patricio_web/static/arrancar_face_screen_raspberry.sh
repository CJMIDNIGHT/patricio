#!/bin/bash
# Arranque de la pantalla facial en Raspberry Pi + LCD físico.
# La Pi muestra face_screen.html a pantalla completa; el rosbridge suele
# estar en el PC del robot (TurtleBot), no en la Pi.
#
# Uso:
#   export PATRICIO_ROS_HOST=192.168.1.50   # IP del PC con ROS 2
#   ./static/arrancar_face_screen_raspberry.sh
#
# Instalación en la Pi (una vez):
#   chmod +x patricio_web/static/arrancar_face_screen_raspberry.sh

set -euo pipefail

WEB_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HTTP_PORT="${PATRICIO_HTTP_PORT:-8000}"
ROS_HOST="${PATRICIO_ROS_HOST:-localhost}"
ROS_PORT="${PATRICIO_ROS_PORT:-9090}"
KIOSK="${PATRICIO_KIOSK:-1}"

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-7}"
export ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-0}"

echo "🖥  Pantalla Patricio — Raspberry Pi + LCD"
echo "    Web:      http://127.0.0.1:${HTTP_PORT}/face_screen.html"
echo "    Rosbridge: ws://${ROS_HOST}:${ROS_PORT}"
echo ""

# Servidor HTTP local (sirve HTML/CSS/imágenes a la LCD)
if ! pgrep -f "python3 -m http.server ${HTTP_PORT}" >/dev/null 2>&1; then
  echo "🌐 Iniciando servidor web en puerto ${HTTP_PORT}..."
  cd "$WEB_DIR"
  nohup python3 -m http.server "$HTTP_PORT" >/tmp/patricio_face_http.log 2>&1 &
  sleep 2
else
  echo "🌐 Servidor web ya activo (puerto ${HTTP_PORT})"
fi

FACE_URL="http://127.0.0.1:${HTTP_PORT}/face_screen.html?ros_host=${ROS_HOST}&ros_port=${ROS_PORT}"

# Ocultar cursor en kiosk (opcional)
if command -v unclutter >/dev/null 2>&1; then
  pkill unclutter 2>/dev/null || true
  unclutter -idle 3 &
fi

echo "🤖 Abriendo pantalla: ${FACE_URL}"

if [[ "$KIOSK" == "1" ]]; then
  if command -v chromium-browser >/dev/null 2>&1; then
    BROWSER=chromium-browser
  elif command -v chromium >/dev/null 2>&1; then
    BROWSER=chromium
  else
    echo "⚠️  Chromium no encontrado. Instala: sudo apt install chromium-browser"
    BROWSER=""
  fi

  if [[ -n "${BROWSER}" ]]; then
    pkill -f "chromium.*face_screen" 2>/dev/null || true
    sleep 1
    "$BROWSER" \
      --kiosk \
      --noerrdialogs \
      --disable-infobars \
      --check-for-update-interval=31536000 \
      --app="${FACE_URL}" &
    exit 0
  fi
fi

# Fallback sin kiosk
if command -v firefox >/dev/null 2>&1; then
  firefox "${FACE_URL}" &
elif command -v chromium-browser >/dev/null 2>&1; then
  chromium-browser "${FACE_URL}" &
else
  echo "Abre manualmente en el navegador: ${FACE_URL}"
fi
