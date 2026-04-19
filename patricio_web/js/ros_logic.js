// ros_logic.js — Pilla-Pilla game logic
// ROS topics:
//   /patricio/pilla_pilla/cmd    (std_msgs/msg/String) ← publish "STOP"
//   /patricio/pilla_pilla/status (std_msgs/msg/String) → subscribe for feedback
// Game START goes via Flask API → ROS service /start_game

let cmdPublisher = null;
let statusSubscriber = null;
let juegoActivo = null;
let esconditeStatusSubscriber = null;

const API_BASE = `http://localhost:5000`;

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
            const poses = obtenerPosesSeleccionadas(); // tu función que recoge los puntos del mapa
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
        const ok = result.started ?? result.success;  // pilla_pilla usa 'started', escondite usa 'success'

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
            body: JSON.stringify({ poses })  // [{ x: 1.0, y: 2.0 }, ...]
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
//pollEstado()
//-----------------------------------------
async function pollEstado(intentos) {
    if (intentos <= 0) return;

    try {
        const res = await fetch(`${API_BASE}/api/juego/estado`);
        const data = await res.json();
        console.log('Poll estado:', data.status);
        handleGameFeedback(data.status);

        // Keep polling while running
        if (data.status.toLowerCase().includes('corriendo')) {
            setTimeout(() => pollEstado(intentos), 3000);
        } else if (data.status.toLowerCase().includes('descansando') && juegoActivo) {
            // Game finished naturally
            setGameButtonState(null, '');
            updateBubble('✅ Patricio ha terminado el juego.');
            juegoActivo = null;
        } else {
            setTimeout(() => pollEstado(intentos - 1), 1000);
        }
    } catch (err) {
        console.error('Poll error:', err);
    }
}

// Called when Stop button is clicked
// Publishes directly to /patricio/pilla_pilla/cmd via rosbridge
async function detenerJuego() {
    // Publish directly via rosbridge
    if (cmdPublisher) {
        const msg = new ROSLIB.Message({ data: 'STOP' });
        cmdPublisher.publish(msg);
        console.log('Publicado STOP en /patricio/pilla_pilla/cmd');
    }

    // Also call API stop as backup
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

    juegoActivo = null;
    setGameButtonState(null, '');
    updateBubble('Patricio está esperando instrucciones...');
}

function updateBubble(texto) {
    const bubble = document.getElementById('juego_status_text');
    if (bubble) bubble.textContent = texto;
}

function setGameButtonState(juego, estado) {
    const btnPilla = document.getElementById('btn_pilla_pilla');
    const btnEscondite = document.getElementById('btn_escondite');
    if (btnPilla) btnPilla.className = 'boton game-btn';
    if (btnEscondite) btnEscondite.className = 'boton game-btn';

    if (!juego) return;

    const btnId = juego === 'pilla_pilla' ? 'btn_pilla_pilla' : 'btn_escondite';
    const btn = document.getElementById(btnId);
    if (btn) btn.classList.add(estado);
}

function handleGameFeedback(estado) {
    const lower = estado.toLowerCase();

    if (lower.includes('corriendo')) {
        setGameButtonState('pilla_pilla', 'juego-activo');
        // Show actual status from node instead of hardcoded text
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
        juegoActivo = null;
    } else if (estado.includes('No puedo llegar') || estado.includes('detenida')) {
        setGameButtonState(null, '');
        juegoActivo = null;
    }
}

function obtenerPosesSeleccionadas() {
    return [
        { x: 1.0, y: 2.0 },
        { x: -1.0, y: 1.5 },
        { x: -1.0, y: 4.0 }
    ];
}