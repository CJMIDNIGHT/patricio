// ros_logic.js — Pilla-Pilla game logic
// ROS topics:
//   /patricio/pilla_pilla/cmd    (std_msgs/msg/String) ← publish "STOP"
//   /patricio/pilla_pilla/status (std_msgs/msg/String) → subscribe for feedback
// Game START goes via Flask API → ROS service /start_game

let cmdPublisher = null;
let statusSubscriber = null;
let juegoActivo = null;

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

    console.log('Tópicos de juego inicializados');
}

// Called when Pilla-Pilla button is clicked
// Calls the Flask API which calls the /start_game ROS service
async function iniciarJuego(juego) {
    if (!cmdPublisher) {
        alert('Conecta con el robot primero.');
        return;
    }

    if (juego !== 'pilla_pilla') {
        updateBubble('⚠️ Solo Pilla-Pilla está disponible por ahora.');
        return;
    }

    juegoActivo = juego;
    setGameButtonState(juego, 'juego-activo');
    updateBubble('Patricio está iniciando Pilla-Pilla...');

    try {
        const response = await fetch(`${API_BASE}/api/juego/iniciar`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ game_name: 'pilla_pilla' })
        });

        const result = await response.json();
        console.log('API response:', result);

        if (!result.started) {
            updateBubble('⚠️ No se pudo iniciar el juego: ' + (result.error || 'error desconocido'));
            setGameButtonState(null, '');
            juegoActivo = null;
        } else {
            // Poll status for a few seconds to catch "Corriendo"
            pollEstado(8);
        }

    } catch (err) {
        console.error('Error llamando a la API:', err);
        updateBubble('❌ No se pudo conectar con la API del juego.');
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