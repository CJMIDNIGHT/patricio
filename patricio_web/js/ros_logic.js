// ros_logic.js — Game logic for Patricio admin panel
// Topics:
//   /patricio/juego  (std_msgs/msg/String) → publish "pilla_pilla" or "escondite"
//   /patricio/estado (std_msgs/msg/String) → subscribe for robot status feedback

let juegoPublisher = null;
let estadoSubscriber = null;
let juegoActivo = null;

function initGameTopics(rosInstance) {
    juegoPublisher = new ROSLIB.Topic({
        ros: rosInstance,
        name: '/patricio/juego',
        messageType: 'std_msgs/msg/String'
    });

    estadoSubscriber = new ROSLIB.Topic({
        ros: rosInstance,
        name: '/patricio/estado',
        messageType: 'std_msgs/msg/String'
    });

    estadoSubscriber.subscribe(function(message) {
        console.log('Estado de Patricio:', message.data);
        updateBubble(message.data);
        handleGameFeedback(message.data);
    });

    console.log('Tópicos de juego inicializados');
}

function publishJuego(juego) {
    if (!juegoPublisher) {
        console.warn('Publisher no inicializado. Conecta primero.');
        return;
    }

    const msg = new ROSLIB.Message({ data: juego });
    juegoPublisher.publish(msg);
    console.log('Publicado en /patricio/juego:', juego);
}

function updateBubble(texto) {
    const bubble = document.getElementById('juego_status_text');
    if (bubble) bubble.textContent = texto;
}

function setGameButtonState(juego, estado) {
    // Reset all buttons
    document.getElementById('btn_pilla_pilla').className = 'boton game-btn';
    document.getElementById('btn_escondite').className = 'boton game-btn';

    if (!juego) return;

    const btnId = juego === 'pilla_pilla' ? 'btn_pilla_pilla' : 'btn_escondite';
    const btn = document.getElementById(btnId);
    if (btn) btn.classList.add(estado);
}

function handleGameFeedback(estado) {
    // Adjust these strings to match what your coworkers publish from patricio_nav_punto
    if (estado.includes('exito') || estado.includes('encontrado')) {
        setGameButtonState(juegoActivo, 'juego-exito');
        updateBubble('Patricio completó el juego con éxito!');
    } else if (estado.includes('fallo') || estado.includes('perdido')) {
        setGameButtonState(juegoActivo, 'juego-fallo');
        updateBubble('Patricio no pudo completar el juego.');
    } else {
        setGameButtonState(juegoActivo, 'juego-activo');
        updateBubble('Patricio está ' + estado);
    }
}

function iniciarJuego(juego) {
    if (!juegoPublisher) {
        alert('Conecta con el robot primero.');
        return;
    }
    juegoActivo = juego;
    setGameButtonState(juego, 'juego-activo');
    updateBubble('Patricio está iniciando ' + (juego === 'pilla_pilla' ? 'Pilla-Pilla' : 'Escondite') + '...');
    publishJuego(juego);
}

function detenerJuego() {
    if (juegoPublisher) {
        const msg = new ROSLIB.Message({ data: 'stop' });
        juegoPublisher.publish(msg);
    }
    juegoActivo = null;
    setGameButtonState(null, '');
    updateBubble('Patricio está esperando instrucciones...');
    console.log('Juego detenido');
}