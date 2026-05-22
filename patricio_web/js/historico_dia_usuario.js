// Resumen diario de juegos (API Flask) para la vista familia — usuario.html
(function () {
  function apiBase() {
    return `http://${window.location.hostname}:5000`;
  }

  function nombreLegible(slug) {
    const map = {
      pilla_pilla: 'Pilla-Pilla',
      escondite: 'Escondite',
      calamar: 'Juego del Calamar',
      'Pilla-Pilla': 'Pilla-Pilla',
      'Escondite': 'Escondite',
      'Juego del Calamar': 'Juego del Calamar',
    };
    return map[slug] || slug || '—';
  }

  function fmtHora(iso) {
    if (!iso) return '—';
    try {
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) return String(iso);
      return d.toLocaleTimeString(undefined, {
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch (_) {
      return String(iso);
    }
  }

  function pintarBarras(agrupado, contenedor) {
    if (!contenedor) return;
    contenedor.innerHTML = '';
    if (!agrupado || agrupado.length === 0) {
      contenedor.innerHTML =
        '<p class="historico-vacio-small">Sin partidas registradas en la base para hoy.</p>';
      return;
    }

    const max = Math.max(...agrupado.map((x) => x.veces), 1);
    agrupado.forEach(({ nombre_juego, veces }) => {
      const row = document.createElement('div');
      row.className = 'historico-bar-fila';
      const pct = Math.round((100 * veces) / max);
      row.innerHTML = `
        <span class="historico-bar-etiqueta">${nombreLegible(nombre_juego)}</span>
        <div class="historico-bar-pista"><div class="historico-bar-relleno" style="width:${pct}%"></div></div>
        <span class="historico-bar-num">${veces}×</span>`;
      contenedor.appendChild(row);
    });
  }

  function pintarTablaDetalle(detalle, tbody) {
    if (!tbody) return;
    tbody.innerHTML = '';

    if (!detalle || detalle.length === 0) {
      const tr = document.createElement('tr');
      tr.innerHTML =
        '<td colspan="4">Hoy no hay partidas registradas. Los juegos que se ejecuten desde el panel de administración aparecerán aquí.</td>';
      tbody.appendChild(tr);
      return;
    }

    detalle.forEach((r) => {
      const tr = document.createElement('tr');
      const juego = r.nombre_actividad || r.nombre_juego;
      tr.innerHTML = `
        <td>${nombreLegible(juego)}</td>
        <td>${fmtHora(r.fecha || r.finalizado_en || r.iniciado_en)}</td>
        <td>${escapeCell(r.puntuacion != null ? r.puntuacion : r.resultado)}</td>
        <td>${escapeCell(r.duracion != null ? r.duracion + ' s' : r.estado)}</td>`;
      tbody.appendChild(tr);
    });
  }

  function pintarModalTabla(detalle, tbodyModal) {
    if (!tbodyModal) return;
    tbodyModal.innerHTML = '';

    if (!detalle || detalle.length === 0) {
      tbodyModal.innerHTML =
        '<tr><td colspan="4">Sin datos del día actual.</td></tr>';
      return;
    }

    let n = detalle.length;
    detalle.forEach((r) => {
      const tr = document.createElement('tr');
      const juego = r.nombre_actividad || r.nombre_juego;
      tr.innerHTML = `
        <td>${String(n--).padStart(3, '0')}</td>
        <td>${fmtHora(r.fecha || r.finalizado_en || r.iniciado_en)}</td>
        <td>${nombreLegible(juego)}</td>
        <td>${escapeCell(r.puntuacion != null ? r.puntuacion : r.resultado)}</td>`;
      tbodyModal.appendChild(tr);
    });
  }

  function escapeCell(s) {
    if (s == null || s === '') return '—';
    const d = document.createElement('div');
    d.textContent = String(s);
    return d.innerHTML;
  }

  async function cargarHistoricoDiaFamilia() {
    const errEl = document.getElementById('historico-dia-error');
    const resumen = document.getElementById('historico-dia-resumen');
    const barras = document.getElementById('historico-dia-barras');
    const tbodyMain = document.getElementById('historico-dia-tabla-body');
    const tbodyModal = document.getElementById('historial-modal-juegos-body');

    if (errEl) {
      errEl.hidden = true;
      errEl.textContent = '';
    }

    try {
      const r = await fetch(`${apiBase()}/api/historico_dia`);
      const data = await r.json();

      if (!data.ok) {
        if (errEl) {
          errEl.hidden = false;
          errEl.textContent =
            data.error || 'No se pudo obtener el histórico. ¿Está activa la API y MySQL?';
        }
        if (resumen) resumen.innerHTML = '<strong>Error al cargar datos.</strong>';
        pintarBarras([], barras);
        pintarTablaDetalle([], tbodyMain);
        pintarModalTabla([], tbodyModal);
        return;
      }

      const agrupado = data.agrupado || [];
      const detalle = data.detalle || [];
      const total = data.total_partidas ?? 0;
      const fav = data.favorito ? nombreLegible(data.favorito) : null;
      const fecha = data.fecha || '';

      if (resumen) {
        resumen.innerHTML =
          `<strong>${total}</strong> partida${total === 1 ? '' : 's'} el <strong>${fecha}</strong>` +
          (fav
            ? ` · Tu juego más repetido hoy: <strong>${fav}</strong>.`
            : total === 0
              ? ' · <em>Juega con Patricio para ver estadísticas aquí.</em>'
              : '');
      }

      pintarBarras(agrupado, barras);
      pintarTablaDetalle(detalle, tbodyMain);
      pintarModalTabla(detalle, tbodyModal);
    } catch (e) {
      console.warn('historico_dia:', e);
      if (errEl) {
        errEl.hidden = false;
        errEl.textContent =
          'Sin conexión con la API (¿http://esta-máquina:5000 encendido?).';
      }
      if (resumen)
        resumen.innerHTML =
          '<strong>No se pudo conectar con la API</strong>';
      pintarBarras([], barras);
      pintarTablaDetalle([], tbodyMain);
      pintarModalTabla([], tbodyModal);
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    cargarHistoricoDiaFamilia();

    const btnHist = document.getElementById('btnHistorialSesiones');
    if (btnHist) {
      btnHist.addEventListener('click', () => {
        cargarHistoricoDiaFamilia();
      });
    }

    setInterval(cargarHistoricoDiaFamilia, 120000);
  });

  window.cargarHistoricoDiaFamilia = cargarHistoricoDiaFamilia;
})();
