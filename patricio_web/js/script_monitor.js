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

  // Conexión con ROSBridge
  const ros = new ROSLIB.Ros({
    url: 'ws://localhost:9090' // Cambia la IP si no está en localhost
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
    timestampEl.textContent = ahora.toLocaleTimeString();
  }

  // 🟡 Batería: suscripción con control de intervalo
  const batteryListener = new ROSLIB.Topic({
    ros: ros,
    name: '/battery_state',
    messageType: 'sensor_msgs/BatteryState'
  });

  let ultimaActualizacionBateria = 0;
  const INTERVALO_BATERIA = 3000;

  batteryListener.subscribe(function (message) {
    const ahora = Date.now();
    if (ahora - ultimaActualizacionBateria >= INTERVALO_BATERIA) {
      ultimaActualizacionBateria = ahora;
      const porcentaje = (message.percentage).toFixed(2);
      bateriaEl.textContent = porcentaje + ' %';
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