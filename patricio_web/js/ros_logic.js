// ros_logic.js — Pilla-Pilla game logic
// ROS topics:
//   /patricio/pilla_pilla/cmd    (std_msgs/msg/String) ← publish "STOP"
//   /patricio/pilla_pilla/status (std_msgs/msg/String) → subscribe for feedback
// Game START goes via Flask API → ROS service /start_game

let cmdPublisher = null;
let statusSubscriber = null;
let juegoActivo = null;
let esconditeStatusSubscriber = null;

const API_BASE = `http://${typeof window !== 'undefined' ? window.location.hostname : 'localhost'}:5000`;

const __debounceGuardadoJuego = {};
function puedeRegistrarJuegoGuardado(nombreJuego, ventanaMs = 4500) {
    const now = Date.now();
    const ult = __debounceGuardadoJuego[nombreJuego];
    if (ult && now - ult < ventanaMs) return false;
    __debounceGuardadoJuego[nombreJuego] = now;
    return true;
}

async function finalizarYGuardarJuegoEnApi(nombreJuego, resultado, estado, detalles) {
    if (!nombreJuego || !puedeRegistrarJuegoGuardado(nombreJuego)) return;
    try {
        const res = await fetch(`${API_BASE}/api/guardar_juego`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                nombre_juego: nombreJuego,
                resultado: resultado,
                estado: estado,
                detalles: detalles || {},
            }),
        });
        const j = await res.json().catch(() => ({}));
        if (!res.ok || !j.ok) {
            console.warn('guardar_juego:', j.error || res.statusText);
        }
    } catch (e) {
        console.warn('guardar_juego red:', e);
    }
}

function initGameTopics(rosInstance) {
    // Publisher for stop commands
    cmdPublisher = new ROSLIB.Topic({
        ros: rosInstance,
        name: '/patricio/pilla_pilla/cmd',
        messageType: 'std_msgs/msg/String'
    });

    // Subscriber for robot status feedback
    statusSubscriber = new ROSLIB.Topic({
        ros: rosInstance,
        name: '/patricio/pilla_pilla/status',
        messageType: 'std_msgs/msg/String'
    });

    statusSubscriber.subscribe(function(message) {
        console.log('Estado pilla_pilla:', message.data);
        handleGameFeedback(message.data);
    });

    esconditeStatusSubscriber = new ROSLIB.Topic({
        ros: rosInstance,
        name: '/patricio/escondite/status',
        messageType: 'std_msgs/msg/String'
    });
    esconditeStatusSubscriber.subscribe(function(message) {
        console.log('Estado escondite:', message.data);
        handleEsconditeFeedback(message.data);
    });

    initCalamarTopics(rosInstance);

    console.log('Tópicos de juego inicializados');
}

// Called when Pilla-Pilla button is clicked
// Calls the Flask API which calls the /start_game ROS service
async function iniciarJuego(juego) {
    if (!cmdPublisher) {
        alert('Conecta con el robot primero.');
        return;
    }

    juegoActivo = juego;
    setGameButtonState(juego, 'juego-activo');
    updateBubble('Patricio está iniciando...');

    try {
        let url, body;

        if (juego === 'pilla_pilla') {
            url  = `${API_BASE}/api/juego/iniciar`;
            body = { game_name: 'pilla_pilla' };

        } else if (juego === 'escondite') {
            const poses = obtenerPosesSeleccionadas();
            if (!poses || poses.length < 2) {
                updateBubble('⚠️ Selecciona al menos 2 puntos en el mapa.');
                setGameButtonState(null, '');
                juegoActivo = null;
                return;
            }
            url  = `${API_BASE}/api/escondite/iniciar`;
            body = { poses };

        } else {
            updateBubble('⚠️ Juego no reconocido.');
            juegoActivo = null;
            return;
        }

        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });

        const result = await response.json();
        const ok = result.started ?? result.success;

        if (!ok) {
            updateBubble('⚠️ ' + (result.error || result.message || 'Error desconocido'));
            setGameButtonState(null, '');
            juegoActivo = null;
        } else {
            if (juego === 'pilla_pilla') pollEstado(8);
            if (juego === 'escondite')   updateBubble('🔍 Patricio está buscando...');
        }

    } catch (err) {
        console.error('Error llamando a la API:', err);
        updateBubble('❌ No se pudo conectar con la API.');
        setGameButtonState(null, '');
        juegoActivo = null;
    }
}

async function iniciarEscondite(poses) {
    if (!poses || poses.length < 2) {
        updateBubble('⚠️ Selecciona al menos 2 puntos en el mapa.');
        return;
    }

    juegoActivo = 'escondite';
    setGameButtonState('escondite', 'juego-activo');
    updateBubble('Patricio está iniciando la búsqueda...');

    try {
        const response = await fetch(`${API_BASE}/api/escondite/iniciar`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ poses })
        });

        const result = await response.json();

        if (!result.success) {
            updateBubble('⚠️ ' + (result.error || result.message));
            setGameButtonState(null, '');
            juegoActivo = null;
        } else {
            const t = result.target_pose?.position;
            console.log(`Objetivo secreto: x=${t?.x}, y=${t?.y}`);
            updateBubble('🔍 Patricio está buscando...');
        }

    } catch (err) {
        updateBubble('❌ No se pudo conectar con la API.');
        setGameButtonState(null, '');
        juegoActivo = null;
    }
}

//-----------------------------------------
// pollEstado()
//-----------------------------------------
async function pollEstado(intentos) {
    if (intentos <= 0) return;

    try {
        const res = await fetch(`${API_BASE}/api/juego/estado`);
        const data = await res.json();
        console.log('Poll estado:', data.status);
        handleGameFeedback(data.status);

        if (data.status.toLowerCase().includes('corriendo')) {
            setTimeout(() => pollEstado(intentos), 3000);
        } else if (data.status.toLowerCase().includes('descansando') && juegoActivo) {
            setGameButtonState(null, '');
            updateBubble('✅ Patricio ha terminado el juego.');
            finalizarYGuardarJuegoEnApi('pilla_pilla', 'completado_natural', 'finalizado_ok', {
                estado_robot: data.status,
            });
            juegoActivo = null;
        } else {
            setTimeout(() => pollEstado(intentos - 1), 1000);
        }
    } catch (err) {
        console.error('Poll error:', err);
    }
}

// Called when Stop button is clicked
async function detenerJuego() {
    const eraJuego = juegoActivo;
    // Publish directly via rosbridge
    // Stop calamar first (handles its own polling + STOP command)
    detenerCalamar();

    // Stop pilla_pilla via rosbridge
    if (cmdPublisher) {
        const msg = new ROSLIB.Message({ data: 'STOP' });
        cmdPublisher.publish(msg);
        console.log('Publicado STOP en /patricio/pilla_pilla/cmd');
    }

    // API stop as backup
    try {
        await fetch(`${API_BASE}/api/juego/detener`, { method: 'POST' });
    } catch(err) {
        console.error('API detener error:', err);
    }

    try {
        await fetch(`${API_BASE}/api/escondite/detener`, { method: 'POST' });
    } catch(err) {
        console.error('Error deteniendo escondite:', err);
    }

    if (eraJuego === 'escondite') {
        await finalizarYGuardarJuegoEnApi('escondite', 'detenido_manual', 'abortado', { origen: 'boton_stop' });
    } else if (eraJuego === 'pilla_pilla') {
        await finalizarYGuardarJuegoEnApi('pilla_pilla', 'detenido_manual', 'abortado', { origen: 'boton_stop' });
    }

    juegoActivo = null;
    setGameButtonState(null, '');
    updateBubble('Patricio está esperando instrucciones...');
}

function updateBubble(texto) {
    const bubble = document.getElementById('juego_status_text');
    if (bubble) bubble.textContent = texto;
}

function setGameButtonState(juego, estado) {
    const btnPilla    = document.getElementById('btn_pilla_pilla');
    const btnEscondite = document.getElementById('btn_escondite');
    const btnCalamar  = document.getElementById('btn_calamar_auto');
    if (btnPilla)     btnPilla.className     = 'boton game-btn';
    if (btnEscondite) btnEscondite.className = 'boton game-btn';
    if (btnCalamar)   btnCalamar.className   = 'boton game-btn';

    if (!juego) return;

    const map = {
        pilla_pilla:  'btn_pilla_pilla',
        escondite:    'btn_escondite',
        calamar:      'btn_calamar_auto'
    };
    const btn = document.getElementById(map[juego]);
    if (btn) btn.classList.add(estado);
}

function handleGameFeedback(estado) {
    const lower = estado.toLowerCase();

    if (lower.includes('corriendo')) {
        setGameButtonState('pilla_pilla', 'juego-activo');
        updateBubble('🏃 Patricio: ' + estado);
        juegoActivo = 'pilla_pilla';
    } else if (lower.includes('descansando')) {
        setGameButtonState(null, '');
        updateBubble('😴 Patricio está descansando...');
        juegoActivo = null;
    } else {
        updateBubble('🤖 Patricio: ' + estado);
    }
}

function handleEsconditeFeedback(estado) {
    updateBubble('🔍 Patricio: ' + estado);

    if (estado.includes('¡Te encontré!')) {
        setGameButtonState(null, '');
        finalizarYGuardarJuegoEnApi('escondite', 'objetivo_encontrado', 'finalizado_ok', {
            texto_estado: estado,
        });
        juegoActivo = null;
    } else if (estado.includes('No puedo llegar') || estado.includes('detenida')) {
        setGameButtonState(null, '');
        finalizarYGuardarJuegoEnApi('escondite', 'sin_exito_nav', 'finalizado_ok', {
            texto_estado: estado,
        });
        juegoActivo = null;
    }
}

function obtenerPosesSeleccionadas() {
    return [
        { x: -1.5, y: 5.5 },
        { x: 5.5,  y: 2.0 },
        { x: 4.0,  y: 4.0 }
    ];
}


// ═══════════════════════════════════════════════════════════════════════════════
// JUEGO DEL CALAMAR — Luz Roja, Luz Verde
// ═══════════════════════════════════════════════════════════════════════════════

let calamarActivo = false;
let calamarPollInterval = null;
let calamarStatusSubscriber = null;
let calamarAlertaSubscriber = null;

/**
 * Inicializa los suscriptores ROS para el juego del calamar.
 * Llamado desde initGameTopics() tras establecer la conexión ROS.
 */
function initCalamarTopics(rosInstance) {
    calamarStatusSubscriber = new ROSLIB.Topic({
        ros: rosInstance,
        name: '/patricio/calamar/status',
        messageType: 'std_msgs/msg/String'
    });
    calamarStatusSubscriber.subscribe(function (message) {
        handleCalamarStatus(message.data);
    });

    calamarAlertaSubscriber = new ROSLIB.Topic({
        ros: rosInstance,
        name: '/patricio/alerta_juego',
        messageType: 'std_msgs/msg/String'
    });
    calamarAlertaSubscriber.subscribe(function (message) {
        if (message.data === 'INFRACCION') {
            mostrarInfraccion();
        }
    });

    console.log('Tópicos del Calamar inicializados');
}

// ── Envío de comandos ─────────────────────────────────────────────────────────

async function enviarComandoCalamar(comando) {
    try {
        const res = await fetch(`${API_BASE}/api/calamar/comando`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ comando })
        });
        const data = await res.json();
        if (!data.ok) {
            console.error('Error enviando comando calamar:', data.error);
            updateBubble('❌ Error: ' + data.error);
        }
    } catch (err) {
        console.error('Error conectando con API calamar:', err);
        updateBubble('❌ No se pudo conectar con la API.');
    }
}

// ── Handlers de botones ───────────────────────────────────────────────────────

/** Botón Modo Automático */
async function iniciarCalamarAuto() {
    calamarActivo = true;
    resetCalamarUI();
    setGameButtonState('calamar', 'juego-activo');
    updateBubble('🦑 Iniciando modo automático...');

    // Mostrar controles manuales
    const controls = document.getElementById('calamar_manual_controls');
    if (controls) controls.style.display = 'flex';

    await enviarComandoCalamar('START_AUTO');
    iniciarPollCalamar();
}

/** Botón Luz Verde (manual) */
async function calamarLuzVerde() {
    calamarActivo = true;
    resetCalamarUI();
    updateBubble('🟢 Luz Verde — ¡Puedes moverte!');
    document.getElementById('juego_bubble').style.backgroundColor = 'rgba(46,125,50,0.35)';
    await enviarComandoCalamar('CAMBIAR_A_VERDE');
}

/** Botón Luz Roja (manual) */
async function calamarLuzRoja() {
    calamarActivo = true;
    updateBubble('🔴 Luz Roja — ¡No te muevas!');
    document.getElementById('juego_bubble').style.backgroundColor = 'rgba(198,40,40,0.35)';
    await enviarComandoCalamar('CAMBIAR_A_ROJO');
}

/** Para cualquier modo — también llamado desde detenerJuego() */
async function detenerCalamar() {
    calamarActivo = false;
    detenerPollCalamar();

    await enviarComandoCalamar('STOP').catch(() => {});

    // Ocultar controles manuales
    const controls = document.getElementById('calamar_manual_controls');
    if (controls) controls.style.display = 'none';

    resetCalamarUI();
    console.log('🦑 Juego del Calamar detenido');
}

// ── Feedback de estado ────────────────────────────────────────────────────────

function handleCalamarStatus(estado) {
    const bubble = document.getElementById('juego_bubble');
    if (!bubble) return;

    // Limpiar clases y estilos anteriores
    bubble.classList.remove('calamar-verde', 'calamar-roja', 'calamar-infraccion');
    bubble.style.backgroundColor = '';
    bubble.style.animation = '';

    switch (estado) {
        case 'LUZ_VERDE':
            bubble.classList.add('calamar-verde');
            updateBubble('🟢 ¡Luz Verde! Puedes moverte');
            break;
        case 'LUZ_ROJA':
            bubble.classList.add('calamar-roja');
            updateBubble('🔴 ¡Luz Roja! No te muevas');
            break;
        case 'INFRACCION':
            mostrarInfraccion();
            break;
        case 'ESPERA':
            updateBubble('🦑 Juego del Calamar — esperando...');
            break;
        default:
            updateBubble('🤖 ' + estado);
    }
}

/** Fondo rojo parpadeante al detectar movimiento. */
function mostrarInfraccion() {
    const bubble = document.getElementById('juego_bubble');
    if (!bubble) return;

    bubble.classList.remove('calamar-verde', 'calamar-roja');
    bubble.classList.add('calamar-infraccion');
    updateBubble('🚨 ¡TE HAS MOVIDO!');

    // Quitar parpadeo después de 3 segundos si el juego sigue activo
    setTimeout(() => {
        if (calamarActivo) {
            bubble.classList.remove('calamar-infraccion');
        }
    }, 3000);
}

/** Restablece la burbuja a estado neutral. */
function resetCalamarUI() {
    const bubble = document.getElementById('juego_bubble');
    if (!bubble) return;
    bubble.classList.remove('calamar-verde', 'calamar-roja', 'calamar-infraccion');
    bubble.style.animation = '';
    bubble.style.backgroundColor = '';
}

// ── Polling de estado via API ─────────────────────────────────────────────────

function iniciarPollCalamar() {
    detenerPollCalamar();
    calamarPollInterval = setInterval(async () => {
        if (!calamarActivo) { detenerPollCalamar(); return; }
        try {
            const res  = await fetch(`${API_BASE}/api/calamar/estado`);
            const data = await res.json();
            handleCalamarStatus(data.status);
            if (data.alerta === 'INFRACCION') mostrarInfraccion();
        } catch (err) {
            console.error('Poll calamar error:', err);
        }
    }, 500);
}

function detenerPollCalamar() {
    if (calamarPollInterval) {
        clearInterval(calamarPollInterval);
        calamarPollInterval = null;
    }
}