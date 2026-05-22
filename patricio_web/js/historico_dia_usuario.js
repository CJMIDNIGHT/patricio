// Historial de partidas (API /api/historico_dia) — usuario.html
(function () {
  const POLL_MS = 120000;
  const PATRICIO_USER_KEY = 'patricio_usuario';

  function apiBase() {
    return `http://${window.location.hostname}:5000`;
  }

  function todayIso() {
    const d = new Date();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${d.getFullYear()}-${m}-${day}`;
  }

  function usuarioIdSesion() {
    try {
      const raw = sessionStorage.getItem(PATRICIO_USER_KEY);
      if (!raw) return null;
      const u = JSON.parse(raw);
      return u.id_usuario != null ? u.id_usuario : u.id;
    } catch (_) {
      return null;
    }
  }

  function nombreLegible(slug) {
    const map = {
      pilla_pilla: 'Pilla-Pilla',
      escondite: 'Escondite',
      calamar: 'Juego del Calamar',
      juego_del_calamar: 'Juego del Calamar',
      alfabeto: 'Alfabeto',
      mates: 'Mates',
      cuentos: 'Cuentos',
      chistes: 'Chistes',
    };
    const key = String(slug || '')
      .trim()
      .toLowerCase()
      .replace(/\s+/g, '_');
    return map[key] || slug || '—';
  }

  function escapeCell(s) {
    if (s == null || s === '') return '—';
    const d = document.createElement('div');
    d.textContent = String(s);
    return d.innerHTML;
  }

  function fmtPuntos(p) {
    if (p == null || p === '') return '—';
    const n = Number(p);
    if (Number.isNaN(n)) return escapeCell(p);
    return Number.isInteger(n) ? String(n) : n.toFixed(1);
  }

  function fmtDuracion(seg) {
    if (seg == null || seg === '') return '—';
    const s = Math.max(0, parseInt(seg, 10) || 0);
    if (s < 60) return `${s} s`;
    const m = Math.floor(s / 60);
    const r = s % 60;
    return r ? `${m} min ${r} s` : `${m} min`;
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
      });
    } catch (_) {
      return String(iso);
    }
  }

  function readFiltrosDom() {
    const fecha = document.getElementById('hist-filtro-fecha');
    const act = document.getElementById('hist-filtro-actividad');
    const orden = document.getElementById('hist-filtro-orden');
    const dmin = document.getElementById('hist-filtro-dur-min');
    const dmax = document.getElementById('hist-filtro-dur-max');
    return {
      fecha: fecha && fecha.value ? fecha.value : todayIso(),
      actividad: act ? act.value : '',
      orden: orden ? orden.value : 'fecha_desc',
      duracionMin: dmin && dmin.value !== '' ? parseInt(dmin.value, 10) : null,
      duracionMax: dmax && dmax.value !== '' ? parseInt(dmax.value, 10) : null,
    };
  }

  function buildQueryParams(f) {
    const p = new URLSearchParams();
    p.set('fecha', f.fecha);
    // Incluye partidas del usuario y las sin asignar (p. ej. registradas desde el panel admin o curl)
    const uid = usuarioIdSesion();
    if (uid != null) p.set('id_usuario', String(uid));
    if (f.actividad) p.set('actividad', f.actividad);
    if (f.orden) p.set('orden', f.orden);
    if (f.duracionMin != null && !Number.isNaN(f.duracionMin)) {
      p.set('duracion_min', String(f.duracionMin));
    }
    if (f.duracionMax != null && !Number.isNaN(f.duracionMax)) {
      p.set('duracion_max', String(f.duracionMax));
    }
    return p.toString();
  }

  function pintarMasJugado(data) {
    const nombreEl = document.getElementById('historico-favorito-nombre');
    const detalleEl = document.getElementById('historico-favorito-detalle');
    const box = document.getElementById('historico-mas-jugado');
    if (!nombreEl || !detalleEl) return;

    const total = data.total_partidas ?? 0;
    const fav = data.favorito;
    const veces = data.favorito_veces ?? 0;

    if (total === 0 || !fav) {
      nombreEl.textContent = 'Sin datos aún';
      detalleEl.textContent =
        'Juega con Patricio desde el panel de administración para ver preferencias.';
      if (box) box.classList.add('historico-mas-jugado--vacio');
      return;
    }

    if (box) box.classList.remove('historico-mas-jugado--vacio');
    nombreEl.textContent = nombreLegible(fav);
    detalleEl.textContent = `${veces} partida${veces === 1 ? '' : 's'} en los filtros actuales · ${total} en total`;
  }

  function pintarResumen(data) {
    const resumen = document.getElementById('historico-dia-resumen');
    if (!resumen) return;
    const total = data.total_partidas ?? 0;
    const fecha = data.fecha || '';
    const filtros = data.filtros_aplicados || {};
    const extras = [];
    if (filtros.actividad) extras.push(`actividad: ${filtros.actividad}`);
    if (filtros.duracion_min != null) extras.push(`duración ≥ ${filtros.duracion_min}s`);
    if (filtros.duracion_max != null) extras.push(`duración ≤ ${filtros.duracion_max}s`);
    if (filtros.orden && filtros.orden !== 'fecha_desc') {
      const ordenTxt = {
        puntuacion_desc: 'mayor puntuación',
        puntuacion_asc: 'menor puntuación',
        duracion_desc: 'mayor duración',
        duracion_asc: 'menor duración',
      };
      extras.push(`orden: ${ordenTxt[filtros.orden] || filtros.orden}`);
    }
    resumen.innerHTML =
      `<strong>${total}</strong> partida${total === 1 ? '' : 's'} el <strong>${fecha}</strong>` +
      (extras.length ? ` · Filtros: ${extras.join(' · ')}` : '');
  }

  function pintarBarras(agrupado, contenedor) {
    if (!contenedor) return;
    contenedor.innerHTML = '';
    if (!agrupado || agrupado.length === 0) {
      contenedor.innerHTML =
        '<p class="historico-vacio-small">Sin partidas con los filtros seleccionados.</p>';
      return;
    }

    const max = Math.max(...agrupado.map((x) => x.veces), 1);
    agrupado.forEach(({ nombre_juego, nombre_actividad, veces }) => {
      const row = document.createElement('div');
      row.className = 'historico-bar-fila';
      const pct = Math.round((100 * veces) / max);
      const nom = nombreLegible(nombre_actividad || nombre_juego);
      row.innerHTML = `
        <span class="historico-bar-etiqueta">${escapeCell(nom)}</span>
        <div class="historico-bar-pista"><div class="historico-bar-relleno" style="width:${pct}%"></div></div>
        <span class="historico-bar-num">${veces}×</span>`;
      contenedor.appendChild(row);
    });
  }

  function pintarTablaPartidos(detalle, tbody) {
    if (!tbody) return;
    tbody.innerHTML = '';

    if (!detalle || detalle.length === 0) {
      tbody.innerHTML =
        '<tr><td colspan="4">No hay partidas con estos filtros. Prueba otra fecha o actividad.</td></tr>';
      return;
    }

    detalle.forEach((r) => {
      const tr = document.createElement('tr');
      const juego = r.nombre_actividad || r.nombre_juego;
      tr.innerHTML = `
        <td>${escapeCell(nombreLegible(juego))}</td>
        <td class="historico-celda-num">${fmtPuntos(r.puntuacion)}</td>
        <td>${escapeCell(fmtDuracion(r.duracion))}</td>
        <td>${escapeCell(fmtFecha(r.fecha || r.finalizado_en || r.iniciado_en))}</td>`;
      tbody.appendChild(tr);
    });
  }

  function pintarModalTabla(detalle, tbodyModal) {
    if (!tbodyModal) return;
    pintarTablaPartidos(detalle, tbodyModal);
  }

  async function cargarHistoricoDiaFamilia() {
    const errEl = document.getElementById('historico-dia-error');
    const barras = document.getElementById('historico-dia-barras');
    const tbodyMain = document.getElementById('historico-dia-tabla-body');
    const tbodyModal = document.getElementById('historial-modal-juegos-body');

    if (errEl) {
      errEl.hidden = true;
      errEl.textContent = '';
    }

    const filtros = readFiltrosDom();
    const qs = buildQueryParams(filtros);

    try {
      const r = await fetch(`${apiBase()}/api/historico_dia?${qs}`);
      const data = await r.json();

      if (!data.ok) {
        if (errEl) {
          errEl.hidden = false;
          errEl.textContent =
            data.error || 'No se pudo obtener el histórico. ¿Está activa la API y MySQL?';
        }
        pintarMasJugado({ total_partidas: 0 });
        pintarResumen({ total_partidas: 0, fecha: filtros.fecha });
        pintarBarras([], barras);
        pintarTablaPartidos([], tbodyMain);
        pintarModalTabla([], tbodyModal);
        return;
      }

      pintarMasJugado(data);
      pintarResumen(data);
      pintarBarras(data.agrupado || [], barras);
      pintarTablaPartidos(data.detalle || [], tbodyMain);
      pintarModalTabla(data.detalle || [], tbodyModal);
    } catch (e) {
      console.warn('historico_dia:', e);
      if (errEl) {
        errEl.hidden = false;
        errEl.textContent =
          'Sin conexión con la API (¿http://esta-máquina:5000 encendido?).';
      }
      pintarMasJugado({ total_partidas: 0 });
      const resumen = document.getElementById('historico-dia-resumen');
      if (resumen) resumen.innerHTML = '<strong>No se pudo conectar con la API</strong>';
      pintarBarras([], barras);
      pintarTablaPartidos([], tbodyMain);
      pintarModalTabla([], tbodyModal);
    }
  }

  function initFiltros() {
    const fechaInput = document.getElementById('hist-filtro-fecha');
    if (fechaInput && !fechaInput.value) fechaInput.value = todayIso();

    const aplicar = () => cargarHistoricoDiaFamilia();
    document.getElementById('hist-btn-aplicar')?.addEventListener('click', aplicar);
    document.getElementById('hist-filtro-fecha')?.addEventListener('change', aplicar);
    document.getElementById('hist-filtro-actividad')?.addEventListener('change', aplicar);
    document.getElementById('hist-filtro-orden')?.addEventListener('change', aplicar);

    document.getElementById('hist-btn-limpiar')?.addEventListener('click', () => {
      const fechaInput = document.getElementById('hist-filtro-fecha');
      const act = document.getElementById('hist-filtro-actividad');
      const orden = document.getElementById('hist-filtro-orden');
      const dmin = document.getElementById('hist-filtro-dur-min');
      const dmax = document.getElementById('hist-filtro-dur-max');
      if (fechaInput) fechaInput.value = todayIso();
      if (act) act.value = '';
      if (orden) orden.value = 'fecha_desc';
      if (dmin) dmin.value = '';
      if (dmax) dmax.value = '';
      aplicar();
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    initFiltros();
    cargarHistoricoDiaFamilia();

    document.getElementById('btnHistorialSesiones')?.addEventListener('click', () => {
      cargarHistoricoDiaFamilia();
    });

    setInterval(cargarHistoricoDiaFamilia, POLL_MS);
  });

  window.cargarHistoricoDiaFamilia = cargarHistoricoDiaFamilia;
})();
