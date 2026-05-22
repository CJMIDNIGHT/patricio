// Panel admin: alertas de incidencias (SQL + Socket.IO en la misma URL que Flask)
(function () {
  function apiBase() {
    return `http://${window.location.hostname}:5000`;
  }

  let socket = null;

  function severityRank(sev) {
    const order = { critico: 0, aviso: 1, info: 2 };
    return order[sev] ?? 99;
  }

  function sortPending(list) {
    return [...list].sort((a, b) => {
      const d = severityRank(a.severidad) - severityRank(b.severidad);
      if (d !== 0) return d;
      return (b.id || 0) - (a.id || 0);
    });
  }

  function escapeHtml(s) {
    if (s == null || s === '') return '';
    const d = document.createElement('div');
    d.textContent = String(s);
    return d.innerHTML;
  }

  function pickActive(list) {
    return sortPending(
      list.filter((x) => !(x.resuelto || x.resuelta))
    );
  }

  function renderBanner(pendingSorted) {
    const el = document.getElementById('incidencias-banner');
    const main = document.querySelector('main');
    if (!el) return;

    const queue = pickActive(pendingSorted);
    document.body.classList.toggle('incidencias-banner-visible', queue.length > 0);
    if (main) main.classList.toggle('incidencias-banner-visible', queue.length > 0);

    if (queue.length === 0) {
      el.innerHTML = '';
      el.classList.add('incidencias-banner--hidden');
      el.setAttribute('aria-hidden', 'true');
      return;
    }

    const current = queue[0];
    const more = queue.length - 1;
    const sev = current.severidad || 'aviso';

    el.classList.remove(
      'incidencias-banner--hidden',
      'incidencias-banner--critico',
      'incidencias-banner--aviso',
      'incidencias-banner--info'
    );
    el.classList.add(`incidencias-banner--${sev}`);
    el.setAttribute('aria-hidden', 'false');

    el.innerHTML = `
      <div class="incidencias-banner__inner">
        <div class="incidencias-banner__text">
          <strong class="incidencias-banner__title">⚠️ Incidencia: ${escapeHtml(current.tipo)}</strong>
          <span class="incidencias-banner__meta">
            Estado: ${escapeHtml(current.estado)}
            · Severidad: ${escapeHtml(sev)}
          </span>
          <p class="incidencias-banner__detail">${escapeHtml(current.descripcion || (current.titulo + ' — ' + current.mensaje))}</p>
          ${more > 0 ? `<p class="incidencias-banner__extra">+ ${more} alerta(s) pendiente(s) en cola.</p>` : ''}
        </div>
        <button type="button" class="boton incidencias-banner__btn" id="btn_incidencia_revisar">
          Aceptar / Revisado
        </button>
      </div>`;

    document.getElementById('btn_incidencia_revisar').addEventListener('click', () => {
      revisarIncidencia(current.id);
    });
  }

  async function fetchPending() {
    const r = await fetch(`${apiBase()}/api/incidencias/pendientes`);
    const j = await r.json();
    if (!j.ok) throw new Error(j.error || 'pendientes');
    return j.incidencias || [];
  }

  async function refreshBanner() {
    try {
      const list = await fetchPending();
      renderBanner(list);
    } catch (e) {
      console.warn('[incidencias] No se pudo cargar pendientes:', e);
    }
  }

  async function revisarIncidencia(id) {
    try {
      const r = await fetch(`${apiBase()}/api/incidencias/${id}/revisar`, {
        method: 'POST',
        headers: { Accept: 'application/json' },
      });
      const j = await r.json();
      if (!j.ok) {
        window.alert(j.error || 'No se pudo marcar como revisado');
        return;
      }
      await refreshBanner();
    } catch (e) {
      console.error(e);
      window.alert('Error de red al marcar la incidencia.');
    }
  }

  function connectSocket() {
    if (typeof io === 'undefined') {
      console.warn('[incidencias] Socket.IO no cargado; solo actualización periódica.');
      return;
    }
    socket = io(apiBase(), { transports: ['websocket', 'polling'] });
    socket.on('connect', () => console.log('[incidencias] Socket.IO conectado'));
    socket.on('disconnect', () => console.warn('[incidencias] Socket.IO desconectado'));
    socket.on('nueva_incidencia', () => {
      refreshBanner();
    });
    socket.on('incidencia_revisada', () => {
      refreshBanner();
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    connectSocket();
    refreshBanner();
    setInterval(refreshBanner, 60000);
  });
})();
