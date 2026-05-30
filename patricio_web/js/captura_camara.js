/**
 * Captura de frame del stream de cámara y descarga local (JPG).
 * Panel admin — criterios T9: canvas oculto, DataURL, sin interrumpir el stream.
 */
(function (global) {
  const FORMAT = 'image/jpeg';
  const QUALITY = 0.92;

  function pad2(n) {
    return String(n).padStart(2, '0');
  }

  function nombreArchivo(ext) {
    const d = new Date();
    return (
      `captura_patricio_${d.getFullYear()}${pad2(d.getMonth() + 1)}${pad2(d.getDate())}_` +
      `${pad2(d.getHours())}${pad2(d.getMinutes())}${pad2(d.getSeconds())}.${ext}`
    );
  }

  function topicDesdeSrc(src) {
    if (!src) return null;
    try {
      const u = new URL(src, window.location.href);
      return u.searchParams.get('topic');
    } catch (_) {
      const m = src.match(/[?&]topic=([^&]+)/);
      return m ? decodeURIComponent(m[1]) : null;
    }
  }

  function descargarDataUrl(dataUrl, filename) {
    const a = document.createElement('a');
    a.href = dataUrl;
    a.download = filename;
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  function pintarFrameEnCanvas(img, canvas) {
    const w = img.naturalWidth || img.width;
    const h = img.naturalHeight || img.height;
    if (!w || !h) return null;
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(img, 0, 0, w, h);
    try {
      return canvas.toDataURL(FORMAT, QUALITY);
    } catch (e) {
      console.warn('[captura] Canvas no exportable (CORS):', e);
      return null;
    }
  }

  function blobAJpegDataUrl(blob, canvas) {
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(blob);
      const tmp = new Image();
      tmp.onload = () => {
        const dataUrl = pintarFrameEnCanvas(tmp, canvas);
        URL.revokeObjectURL(url);
        if (dataUrl) resolve(dataUrl);
        else reject(new Error('No se pudo convertir la imagen'));
      };
      tmp.onerror = () => {
        URL.revokeObjectURL(url);
        reject(new Error('Error al cargar snapshot'));
      };
      tmp.src = url;
    });
  }

  async function capturarDesdeSnapshot(host, topic, canvas) {
    const t = encodeURIComponent(topic);
    const snapUrl = `http://${host}:8080/snapshot?topic=${t}&t=${Date.now()}`;
    const resp = await fetch(snapUrl, { mode: 'cors', cache: 'no-store' });
    if (!resp.ok) throw new Error(`Snapshot HTTP ${resp.status}`);
    const blob = await resp.blob();
    return blobAJpegDataUrl(blob, canvas);
  }

  async function congelarFrame(img, canvas) {
    if (!img || !canvas) throw new Error('Elementos de cámara no encontrados');

    const host = window.location.hostname;
    const topic =
      topicDesdeSrc(img.src) || '/patricio/camera_processed';

    if (img.complete && (img.naturalWidth || img.width) > 0) {
      const dataUrl = pintarFrameEnCanvas(img, canvas);
      if (dataUrl) return dataUrl;
    }

    return capturarDesdeSnapshot(host, topic, canvas);
  }

  function feedback(el, msg, ok) {
    if (!el) return;
    el.hidden = false;
    el.textContent = msg;
    el.classList.toggle('captura-feedback--ok', !!ok);
    el.classList.toggle('captura-feedback--err', !ok);
    clearTimeout(el._capturaT);
    el._capturaT = setTimeout(() => {
      el.hidden = true;
    }, 3500);
  }

  function flashContenedor(wrap) {
    if (!wrap) return;
    wrap.classList.remove('camera-capture-wrap--flash');
    void wrap.offsetWidth;
    wrap.classList.add('camera-capture-wrap--flash');
    setTimeout(() => wrap.classList.remove('camera-capture-wrap--flash'), 450);
  }

  function init(options) {
    const btn = document.getElementById(options.btnId || 'btn_guardar_imagen');
    const img = document.getElementById(options.imgId || 'cameraFeed');
    const canvas = document.getElementById(options.canvasId || 'captureCanvas');
    const wrap = document.getElementById(options.wrapId || 'divCamera');
    const fb = document.getElementById(options.feedbackId || 'captura-feedback');

    if (!btn || !img || !canvas) {
      console.warn('[captura] Botón, imagen o canvas no encontrados');
      return;
    }

    btn.addEventListener('click', async () => {
      if (!img.src || img.src === window.location.href) {
        feedback(fb, 'Activa la cámara (Conectar) antes de capturar.', false);
        return;
      }

      const prevLabel = btn.textContent;
      btn.disabled = true;
      btn.textContent = 'Capturando…';

      try {
        const dataUrl = await congelarFrame(img, canvas);
        const nombre = nombreArchivo('jpg');
        descargarDataUrl(dataUrl, nombre);
        flashContenedor(wrap);
        feedback(fb, `Descargado: ${nombre}`, true);
      } catch (e) {
        console.error('[captura]', e);
        feedback(
          fb,
          'No se pudo capturar. ¿web_video_server en :8080 y cámara conectada?',
          false
        );
      } finally {
        btn.disabled = false;
        btn.textContent = prevLabel;
      }
    });
  }

  global.PatricioCaptura = { init, congelarFrame, nombreArchivo };
})(window);

document.addEventListener('DOMContentLoaded', () => {
  if (document.getElementById('btn_guardar_imagen')) {
    PatricioCaptura.init({});
  }
});
