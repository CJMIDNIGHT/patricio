// Panel admin: banner + tabla de incidencias (SQL + Socket.IO + polling)
(function () {
  const POLL_MS = 15000;

  function apiBase() {
    return `http://${window.location.hostname}:5000`;
  }

  let socket = null;
  let pollTimer = null;
  let filtros = buildDefaultFiltros();

  function todayIso() {
    const d = new Date();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${d.getFullYear()}-${m}-${day}`;
  }

  function buildDefaultFiltros() {
    return {
      soloHoy: true,
      fechaDesde: '',
      fechaHasta: '',
      estado: '',
      q: '',
    };
  }

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
    return sortPending(list.filter((x) => !(x.resuelto || x.resuelta)));
  }

  function estadoEtiqueta(inc) {
    if (inc.resuelto || inc.resuelta) return 'Resuelto';
    return 'Pendiente';
  }

  function incidenciaTexto(inc) {
    const tipo = (inc.tipo || inc.titulo || 'Incidencia').trim();
    const desc = (inc.descripcion || inc.mensaje || '').trim();
    if (desc && desc !== tipo) return `${tipo}: ${desc}`;
    return tipo;
  }

  function fmtFecha(iso) {
    if (!iso) return '—';
    try {
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) return String(iso);
      return d.toLocaleString(undefined, {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      });
    } catch (_) {
      return String(iso);
    }
  }

  function readFiltrosFromDom() {
    const soloHoy = document.getElementById('filtro_solo_hoy');
    const fd = document.getElementById('filtro_fecha_desde');
    const fh = document.getElementById('filtro_fecha_hasta');
    const est = document.getElementById('filtro_estado');
    const q = document.getElementById('filtro_busqueda');
    filtros = {
      soloHoy: !!(soloHoy && soloHoy.checked),
      fechaDesde: fd ? fd.value : '',
      fechaHasta: fh ? fh.value : '',
      estado: est ? est.value : '',
      q: q ? q.value.trim() : '',
    };
    return filtros;
  }

  function syncFiltrosDom() {
    const soloHoy = document.getElementById('filtro_solo_hoy');
    const fd = document.getElementById('filtro_fecha_desde');
    const fh = document.getElementById('filtro_fecha_hasta');
    const est = document.getElementById('filtro_estado');
    const q = document.getElementById('filtro_busqueda');
    if (soloHoy) soloHoy.checked = filtros.soloHoy;
    if (fd) {
      fd.disabled = filtros.soloHoy;
      fd.value = filtros.fechaDesde;
    }
    if (fh) {
      fh.disabled = filtros.soloHoy;
      fh.value = filtros.fechaHasta;
    }
    if (est) est.value = filtros.estado;
    if (q) q.value = filtros.q;
  }

  function buildQueryParams() {
    const p = new URLSearchParams();
    if (filtros.soloHoy) {
      p.set('fecha', todayIso());
    } else {
      if (filtros.fechaDesde) p.set('fecha_desde', filtros.fechaDesde);
      if (filtros.fechaHasta) p.set('fecha_hasta', filtros.fechaHasta);
    }
    if (filtros.estado) p.set('estado', filtros.estado);
    if (filtros.q) p.set('q', filtros.q);
    return p.toString();
  }

  async function fetchIncidenciasList() {
    const qs = buildQueryParams();
    const url = `${apiBase()}/api/incidencias${qs ? `?${qs}` : ''}`;
    const r = await fetch(url);
    const j = await r.json();
    if (!j.ok) throw new Error(j.error || 'listado incidencias');
    return j.incidencias || [];
  }

  async function fetchPending() {
    const r = await fetch(`${apiBase()}/api/incidencias/pendientes`);
    const j = await r.json();
    if (!j.ok) throw new Error(j.error || 'pendientes');
    return j.incidencias || [];
  }

  function setLiveIndicator(on) {
    const el = document.getElementById('incidencias-live-indicator');
    if (!el) return;
    el.classList.toggle('incidencias-live--on', on);
    el.classList.toggle('incidencias-live--off', !on);
    el.textContent = on ? '● En vivo' : '○ Sin conexión en vivo';
  }

  function renderTabla(list) {
    const tbody = document.getElementById('incidencias-tabla-body');
    const resumen = document.getElementById('incidencias-tabla-resumen');
    const errEl = document.getElementById('incidencias-tabla-error');
    if (!tbody) return;

    if (errEl) {
      errEl.hidden = true;
      errEl.textContent = '';
    }

    tbody.innerHTML = '';
    if (!list || list.length === 0) {
      tbody.innerHTML =
        '<tr><td colspan="4">No hay incidencias con los filtros seleccionados.</td></tr>';
      if (resumen) resumen.textContent = '0 incidencias';
      return;
    }

    const pendientes = list.filter((x) => !(x.resuelto || x.resuelta)).length;
    if (resumen) {
      resumen.textContent = `${list.length} incidencia(s) · ${pendientes} pendiente(s)`;
    }

    list.forEach((inc) => {
      const tr = document.createElement('tr');
      const resuelta = !!(inc.resuelto || inc.resuelta);
      const estado = estadoEtiqueta(inc);
      const estadoClass = resuelta
        ? 'incidencias-estado incidencias-estado--resuelto'
        : 'incidencias-estado incidencias-estado--pendiente';

      tr.innerHTML = `
        <td class="incidencias-celda-texto">${escapeHtml(incidenciaTexto(inc))}</td>
        <td>${escapeHtml(fmtFecha(inc.fecha))}</td>
        <td><span class="${estadoClass}">${escapeHtml(estado)}</span></td>
        <td class="incidencias-celda-accion"></td>`;

      const accionTd = tr.querySelector('.incidencias-celda-accion');
      if (!resuelta && inc.id != null) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'boton incidencias-btn-tabla';
        btn.textContent = 'Marcar resuelta';
        btn.addEventListener('click', () => revisarIncidencia(inc.id));
        accionTd.appendChild(btn);
      } else {
        accionTd.textContent = '—';
      }
      tbody.appendChild(tr);
    });
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
            Estado: ${escapeHtml(estadoEtiqueta(current))}
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

  async function refreshAll() {
    try {
      const [list, pending] = await Promise.all([
        fetchIncidenciasList().catch((e) => {
          console.warn('[incidencias] tabla:', e);
          return null;
        }),
        fetchPending(),
      ]);
      renderBanner(pending);
      if (list !== null) renderTabla(list);
    } catch (e) {
      console.warn('[incidencias] No se pudo cargar pendientes:', e);
    }
  }

  async function refreshTabla() {
    const tbody = document.getElementById('incidencias-tabla-body');
    const errEl = document.getElementById('incidencias-tabla-error');
    try {
      const list = await fetchIncidenciasList();
      renderTabla(list);
    } catch (e) {
      console.warn('[incidencias] tabla:', e);
      if (tbody) {
        tbody.innerHTML =
          '<tr><td colspan="4">No se pudo cargar la tabla. Comprueba que la API Flask esté en marcha (puerto 5000).</td></tr>';
      }
      if (errEl) {
        errEl.hidden = false;
        errEl.textContent = String(e.message || e);
      }
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
      await refreshAll();
    } catch (e) {
      console.error(e);
      window.alert('Error de red al marcar la incidencia.');
    }
  }

  function connectSocket() {
    if (typeof io === 'undefined') {
      console.warn('[incidencias] Socket.IO no cargado; solo polling.');
      setLiveIndicator(false);
      return;
    }
    socket = io(apiBase(), { transports: ['websocket', 'polling'] });
    socket.on('connect', () => {
      console.log('[incidencias] Socket.IO conectado');
      setLiveIndicator(true);
    });
    socket.on('disconnect', () => {
      console.warn('[incidencias] Socket.IO desconectado');
      setLiveIndicator(false);
    });
    socket.on('nueva_incidencia', () => refreshAll());
    socket.on('incidencia_revisada', () => refreshAll());
  }

  function wireFiltros() {
    const soloHoy = document.getElementById('filtro_solo_hoy');
    const fd = document.getElementById('filtro_fecha_desde');
    const fh = document.getElementById('filtro_fecha_hasta');
    const btnApply = document.getElementById('btn_incidencias_aplicar');
    const btnClear = document.getElementById('btn_incidencias_limpiar');
    const busqueda = document.getElementById('filtro_busqueda');
    const estado = document.getElementById('filtro_estado');

    function onSoloHoyChange() {
      readFiltrosFromDom();
      if (fd) fd.disabled = filtros.soloHoy;
      if (fh) fh.disabled = filtros.soloHoy;
    }

    if (soloHoy) soloHoy.addEventListener('change', onSoloHoyChange);

    const aplicar = () => {
      readFiltrosFromDom();
      refreshTabla();
    };

    if (btnApply) btnApply.addEventListener('click', aplicar);
    if (estado) estado.addEventListener('change', aplicar);
    if (busqueda) {
      let debounce;
      busqueda.addEventListener('input', () => {
        clearTimeout(debounce);
        debounce = setTimeout(aplicar, 400);
      });
    }
    if (fd) fd.addEventListener('change', aplicar);
    if (fh) fh.addEventListener('change', aplicar);

    if (btnClear) {
      btnClear.addEventListener('click', () => {
        filtros = buildDefaultFiltros();
        syncFiltrosDom();
        onSoloHoyChange();
        refreshTabla();
      });
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    syncFiltrosDom();
    wireFiltros();
    connectSocket();
    refreshAll();
    pollTimer = setInterval(refreshAll, POLL_MS);
  });
})();
