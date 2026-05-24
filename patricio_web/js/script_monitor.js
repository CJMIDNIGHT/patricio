  // Referencias a elementos HTML
  const bateriaEl = document.getElementById('bateria');
  const velocidadEl = document.getElementById('velocidad');
  const temperaturaEl = document.getElementById('temperatura');
  const timestampEl = document.getElementById('timestamp');

  // Mostrar "No disponible" al inicio
  function setNoDisponible() {
    bateriaEl.textContent = 'No disponible';
    velocidadEl.textContent = 'No disponible';
    temperaturaEl.textContent = 'No disponible';
    timestampEl.textContent = 'No disponible';
  }

  setNoDisponible();

  const rosHost = window.location.hostname || 'localhost';
  const apiIncidencias = () => `http://${rosHost}:5000`;

  // Conexión con ROSBridge (mismo host que la página admin)
  const ros = new ROSLIB.Ros({
    url: `ws://${rosHost}:9090`
  });

  ros.on('connection', () => {
    console.log('✅ Conectado a ROSBridge websocket');
  });

  ros.on('error', (error) => {
    console.error('❌ Error de conexión:', error);
    setNoDisponible();
  });

  ros.on('close', () => {
    console.warn('⚠️ Conexión ROSBridge cerrada');
    setNoDisponible();
  });

  // Función para actualizar timestamp
  function actualizarTimestamp() {
    const ahora = new Date();
    timestampEl.textContent =
      typeof PatricioFecha !== 'undefined'
        ? PatricioFecha.fmtDmyHora(ahora, true)
        : ahora.toLocaleString('es-ES');
  }

  // 🟡 Batería: suscripción con control de intervalo
  const batteryListener = new ROSLIB.Topic({
    ros: ros,
    name: '/battery_state',
    messageType: 'sensor_msgs/BatteryState'
  });

  let ultimaActualizacionBateria = 0;
  const INTERVALO_BATERIA = 3000;
  let ultimaAlertaBateriaMs = 0;
  const MIN_MS_ENTRE_ALERTAS_BAT = 120000;
  const UMBRAL_BAT_FRAC = 0.2;

  batteryListener.subscribe(function (message) {
    const ahora = Date.now();
    const p = message.percentage;
    if (p != null && !isNaN(Number(p))) {
      const frac = Number(p) <= 1 ? Number(p) : Number(p) / 100;
      if (
        frac < UMBRAL_BAT_FRAC &&
        ahora - ultimaAlertaBateriaMs >= MIN_MS_ENTRE_ALERTAS_BAT
      ) {
        ultimaAlertaBateriaMs = ahora;
        const pctStr = (frac * 100).toFixed(0);
        fetch(`${apiIncidencias()}/api/incidencias`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            tipo: 'Batería baja',
            titulo: 'Batería baja detectada',
            mensaje: `Nivel aproximado ${pctStr} %`,
            severidad: 'critico',
          }),
        }).catch(() => {});
      }
    }
    if (ahora - ultimaActualizacionBateria >= INTERVALO_BATERIA) {
      ultimaActualizacionBateria = ahora;
      const porcentaje =
        p != null && !isNaN(Number(p))
          ? (Number(p) <= 1 ? (Number(p) * 100).toFixed(0) : Number(p).toFixed(0))
          : '?';
      bateriaEl.textContent = porcentaje + ' %';
    }
  });

  // Anomalías publicadas desde el robot (JSON en data): tipo, mensaje, titulo, severidad opcional
  const incRosListener = new ROSLIB.Topic({
    ros: ros,
    name: '/patricio/incidencia',
    messageType: 'std_msgs/msg/String',
  });

  incRosListener.subscribe(function (message) {
    try {
      const raw = typeof message.data === 'string' ? message.data.trim() : '';
      if (!raw) return;
      const payload = JSON.parse(raw);
      const tipo = (payload.tipo || payload.type || '').trim();
      if (!tipo) return;
      fetch(`${apiIncidencias()}/api/incidencias`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tipo,
          titulo: (payload.titulo || tipo).substring(0, 200),
          mensaje:
            payload.mensaje ||
            payload.message ||
            'Sin detalle adicional',
          severidad: payload.severidad || 'aviso',
        }),
      }).catch(() => {});
    } catch (_) {
      /* JSON inválido: ignorar */
    }
  });

  // 🔵 Velocidad: /cmd_vel -> linear.x
  const cmdVelListener = new ROSLIB.Topic({
    ros: ros,
    name: '/cmd_vel',
    messageType: 'geometry_msgs/msg/Twist'
  });

  cmdVelListener.subscribe(function (message) {
    const velocidadLineal = message.linear.x.toFixed(2);
    velocidadEl.textContent = velocidadLineal + ' m/s';
    actualizarTimestamp();
  });

  // 🔴 Temperatura: /temperature (std_msgs/msg/Float32)
  const tempListener = new ROSLIB.Topic({
    ros: ros,
    name: '/temperature',
    messageType: 'std_msgs/msg/Float32'
  });

  tempListener.subscribe(function (message) {
    const temperatura = message.data.toFixed(1);
    temperaturaEl.textContent = temperatura + ' °C';
    actualizarTimestamp();
  });