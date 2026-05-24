// Formato de fechas Patricio: día/mes/año (es-ES)
(function (global) {
  const LOCALE = 'es-ES';

  function parseDate(value) {
    if (value == null || value === '') return null;
    if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value.trim())) {
      const [y, m, d] = value.trim().split('-').map(Number);
      const dt = new Date(y, m - 1, d);
      return Number.isNaN(dt.getTime()) ? null : dt;
    }
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? null : d;
  }

  function fmtDmy(value) {
    const d = parseDate(value);
    if (!d) return value == null || value === '' ? '—' : String(value);
    return d.toLocaleDateString(LOCALE, {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    });
  }

  function fmtDmyHora(value, withSeconds) {
    const d = parseDate(value);
    if (!d) return value == null || value === '' ? '—' : String(value);
    const opts = {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    };
    if (withSeconds) opts.second = '2-digit';
    return d.toLocaleString(LOCALE, opts);
  }

  global.PatricioFecha = {
    fmtDmy,
    fmtDmyHora,
  };
})(typeof window !== 'undefined' ? window : globalThis);
