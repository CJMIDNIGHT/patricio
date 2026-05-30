# Guía paso a paso — Captura de foto desde la interfaz web (Patricio)

Esta guía explica cómo instalar, arrancar y probar la **captura manual de imagen** en el panel de administración (`admin.html`): congelar el frame del stream de cámara, guardarlo como JPG en tu ordenador o móvil, sin interrumpir el vídeo en vivo.

---

## 1. Qué hace esta función

| Elemento | Descripción |
|----------|-------------|
| **Interfaz** | Panel admin → sección «Vista de cámara» |
| **Botón** | «📷 Capturar y descargar» |
| **Stream** | `http://HOST:8080/stream?topic=/patricio/camera_processed` |
| **Técnica** | Canvas oculto + DataURL JPEG + descarga automática |
| **Archivo** | `captura_patricio_AAAAMMDD_HHMMSS.jpg` |

**Requisitos:** algo publicando imágenes en ROS, `web_video_server` (puerto 8080) y servidor web estático (puerto 8000).

---

## 2. Arquitectura (resumen)

```
[Cámara / Gazebo / Webcam]
        ↓
  vision_node (opcional)
        ↓
  /patricio/camera_processed
        ↓
  web_video_server :8080  ← stream MJPEG
        ↓
  admin.html :8000  ← <img id="cameraFeed">
        ↓
  captura_camara.js  ← canvas + descarga JPG
```

---

## 3. Requisitos previos

- **ROS 2** (Jazzy o Humble) con workspace compilado.
- Paquetes: `patricio_captacion` (cámara procesada), `web_video_server`.
- Navegador moderno (Chrome, Firefox, Edge).
- Usuario admin de prueba: `admin@patricio.local` / `1234` (tras `seed_usuarios_prueba.sql`).

---

## 4. Compilar (una vez)

```bash
cd ~/turtlebot3_ws
source /opt/ros/jazzy/setup.bash
colcon build --packages-select patricio_captacion --symlink-install
source install/setup.bash
```

---

## 5. Arranque paso a paso

Necesitas **3–4 terminales** (más Gazebo si usas simulación).

### Terminal 1 — Imagen en ROS

**Opción A — Simulación Gazebo**

```bash
source ~/turtlebot3_ws/install/setup.bash
export ROS_DOMAIN_ID=7
export TURTLEBOT3_MODEL=burger_cam
ros2 launch patricio_my_world house.launch.py
```

En otra terminal, visión (procesa y publica `/patricio/camera_processed`):

```bash
source ~/turtlebot3_ws/install/setup.bash
ros2 launch patricio_captacion vision.launch.py
```

**Opción B — Webcam del PC (sin Gazebo)**

```bash
# Terminal 1a
source ~/turtlebot3_ws/install/setup.bash
ros2 run patricio_captacion webcam_publisher_linux

# Terminal 1b
source ~/turtlebot3_ws/install/setup.bash
ros2 launch patricio_captacion vision.launch.py
```

**Comprobar que hay imagen:**

```bash
source ~/turtlebot3_ws/install/setup.bash
ros2 topic hz /patricio/camera_processed
```

Debe mostrar frecuencia (varios Hz). Si no hay publicador, la captura no tendrá imagen.

---

### Terminal 2 — web_video_server (puerto 8080)

```bash
source ~/turtlebot3_ws/install/setup.bash
ros2 run web_video_server web_video_server
```

**Prueba en el navegador** (sustituye `127.0.0.1` por la IP del robot si hace falta):

```
http://127.0.0.1:8080/stream?topic=/patricio/camera_processed
```

Debes ver **vídeo en movimiento**. Si no, no sigas hasta arreglar esto.

**Prueba snapshot** (usado como respaldo al capturar):

```
http://127.0.0.1:8080/snapshot?topic=/patricio/camera_processed
```

Debe mostrar **una imagen JPEG**, no error 404.

---

### Terminal 3 — Servidor web (puerto 8000)

```bash
cd ~/turtlebot3_ws/src/patricio/patricio_web
python3 -m http.server 8000
```

---

### Terminal 4 — rosbridge (opcional, para «Conectar» completo)

```bash
source ~/turtlebot3_ws/install/setup.bash
ros2 launch rosbridge_server rosbridge_websocket_launch.xml
```

La **captura de foto** depende sobre todo del stream en 8080; rosbridge es para mapa, robot y juegos.

---

## 6. Probar en el navegador

### 6.1 Abrir admin

```
http://127.0.0.1:8000/admin.html
```

Desde otro dispositivo en la red: `http://IP_DEL_ROBOT:8000/admin.html`

### 6.2 Iniciar sesión

- Email: `admin@patricio.local`
- Contraseña: `1234`

### 6.3 Conectar

1. En «Dirección del servidor»: `ws://127.0.0.1:9090` (o IP correcta).
2. Pulsa **Conectar**.
3. Estado: **Conectado** (verde) si rosbridge responde.
4. En **Vista de cámara** debe aparecer el **stream en vivo**.

> Al conectar se llama a `activarCamara()` y se asigna el stream a `/patricio/camera_processed`.

### 6.4 Capturar y descargar

1. Con el vídeo visible, pulsa **📷 Capturar y descargar**.
2. Esperado:
   - Flash blanco breve (el vídeo **no se para**).
   - Mensaje verde: `Descargado: captura_patricio_....jpg`
   - Archivo en la carpeta **Descargas** del navegador.
3. El stream debe **seguir en vivo** después de capturar.

Ejemplo de nombre:

```
captura_patricio_20260524_153045.jpg
```

---

## 7. Criterios de validación (checklist)

Marca cuando funcione:

- [ ] `ros2 topic hz /patricio/camera_processed` muestra datos
- [ ] URL del stream en :8080 muestra vídeo
- [ ] URL snapshot en :8080 muestra una foto
- [ ] `admin.html` muestra cámara en vivo tras **Conectar**
- [ ] Botón descarga un `.jpg` con nombre `captura_patricio_...`
- [ ] El vídeo **no se congela** tras capturar (solo flash momentáneo)
- [ ] Mensaje de error claro si la cámara no está activa

---

## 8. Arranque automático (script del proyecto)

Si ya usas el lanzador completo:

```bash
cd ~/turtlebot3_ws/src/patricio/patricio_web/static
./arrancar_web.sh
```

Abre terminales de Gazebo, rosbridge, `web_video_server`, HTTP 8000, API, etc. Luego entra a `admin.html` y prueba el botón.

---

## 9. Comprobar sin navegador (terminal)

```bash
curl -s -o /tmp/test_snapshot.jpg \
  "http://127.0.0.1:8080/snapshot?topic=/patricio/camera_processed"
file /tmp/test_snapshot.jpg
```

Salida esperada: `JPEG image data`.

---

## 10. Archivos del proyecto (referencia)

| Archivo | Función |
|---------|---------|
| `admin.html` | Botón, `<img id="cameraFeed">`, `<canvas id="captureCanvas" hidden>` |
| `js/captura_camara.js` | Listener, canvas, DataURL, descarga |
| `js/script_admin.js` | `activarCamara()` al conectar |
| `css/styles_admin.css` | Estilos botón, flash, feedback |

---

## 11. Resolución de problemas

### Pantalla negra en «Vista de cámara»

- ¿`web_video_server` en marcha?
- ¿`/patricio/camera_processed` publicando? → `ros2 topic hz ...`
- Prueba la URL del stream directamente en el navegador.

### «Activa la cámara (Conectar) antes de capturar»

- Pulsa **Conectar** en admin (asigna `src` al `<img>`).

### «No se pudo capturar…»

- Comprueba snapshot con `curl` (sección 9).
- Reinicia `web_video_server`.
- Cierra otras apps que usen la cámara (si usas webcam).

### No aparece la descarga

- Revisa permisos de descargas del navegador.
- Prueba otro navegador.
- Modo incógnito a veces bloquea descargas múltiples.

### El vídeo se corta tras capturar

- No debería ocurrir con la versión actual (no se cambia `img.src`).
- Recarga la página y **Conectar** de nuevo.

### CORS entre puertos 8000 y 8080

- La app intenta primero canvas desde el `<img>`.
- Si falla, usa **snapshot** en `:8080` automáticamente.

---

## 12. Comandos de referencia rápida

```bash
# Entorno
source /opt/ros/jazzy/setup.bash
source ~/turtlebot3_ws/install/setup.bash

# Comprobar imagen ROS
ros2 topic hz /patricio/camera_processed

# Stream web
ros2 run web_video_server web_video_server

# Web estática
cd ~/turtlebot3_ws/src/patricio/patricio_web && python3 -m http.server 8000

# Snapshot de prueba
curl -s -o /tmp/captura.jpg \
  "http://127.0.0.1:8080/snapshot?topic=/patricio/camera_processed"
```

**Navegador:** `http://127.0.0.1:8000/admin.html` → Conectar → 📷 Capturar y descargar

---

*Guía asociada a la tarea H11-T9 — Control de captura de foto desde la interfaz web · Patricio 2026.*
