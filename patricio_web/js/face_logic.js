// ==========================
// FACE SCREEN LOGIC
// ==========================

let ros = null;

let faceSubscriber = null;

let gameSubscriber = null;

let inactivityTimeout = null;

let gameTimeout = null;

// ==========================
// ROSBRIDGE
// ==========================

const ROSBRIDGE_URL = `ws://${window.location.hostname}:9090`;

// ==========================
// ESTADO ACTUAL
// ==========================

let currentEmotion = "happy";

let currentGame = "none";

// ==========================
// CONEXIÓN ROS
// ==========================

function connectROS() {

    ros = new ROSLIB.Ros({

        url: ROSBRIDGE_URL
    });

    // --------------------------
    // CONECTADO
    // --------------------------

    ros.on('connection', () => {

        console.log('Conectado a rosbridge');

        updateUI();

        subscribeFaceTopic();

        subscribeGameTopic();
    });

    // --------------------------
    // ERROR
    // --------------------------

    ros.on('error', (error) => {

        console.error('Error ROS:', error);

        setDisconnected();
    });

    // --------------------------
    // DESCONECTADO
    // --------------------------

    ros.on('close', () => {

        console.warn('Conexión cerrada');

        setDisconnected();
    });
}

// ==========================
// TOPIC EMOCIONES
// ==========================

function subscribeFaceTopic() {

    faceSubscriber = new ROSLIB.Topic({

        ros: ros,

        name: '/patricio/face_status',

        messageType: 'std_msgs/msg/String'
    });

    faceSubscriber.subscribe((message) => {

        console.log('Face status:', message.data);

        clearTimeout(inactivityTimeout);

        currentEmotion = message.data;

        updateUI();

        // volver a happy tras 5 segundos
        inactivityTimeout = setTimeout(() => {

            currentEmotion = "happy";

            updateUI();

        }, 5000);
    });
}

// ==========================
// TOPIC JUEGO ACTIVO
// ==========================

function subscribeGameTopic() {

    gameSubscriber = new ROSLIB.Topic({

        ros: ros,

        name: '/patricio/game_status',

        messageType: 'std_msgs/msg/String'
    });

    gameSubscriber.subscribe((message) => {

        console.log('Game status:', message.data);

        clearTimeout(gameTimeout);

        currentGame = message.data;

        updateUI();

        // volver a none tras 5 segundos
        gameTimeout = setTimeout(() => {

            currentGame = "none";

            updateUI();

        }, 5000);
    });
}

// ==========================
// ACTUALIZAR UI
// ==========================

function updateUI() {

    updateFace();

    updateGameIndicator();
}

// ==========================
// ACTUALIZAR CARA
// ==========================

function updateFace() {

    switch(currentEmotion) {

        // --------------------------
        // FELIZ
        // --------------------------

        case 'happy':

            setFaceImage(
                'cara_feliz.png',
                'Patricio está feliz 😊'
            );

            break;

        // --------------------------
        // CONCENTRADO
        // --------------------------

        case 'focus':

            setFaceImage(
                'cara_concentrado.png',
                'Patricio está concentrado 👀'
            );

            break;

        // --------------------------
        // ALERTA
        // --------------------------

        case 'alert':

            setFaceImage(
                'cara_sorprendido.png',
                'Patricio está en alerta ⚠️'
            );

            break;

        // --------------------------
        // TRISTE
        // --------------------------

        case 'sad':

            setFaceImage(
                'cara_triste.png',
                'Patricio está triste 😢'
            );

            break;

        // --------------------------
        // DESCONECTADO
        // --------------------------

        case 'disconnected':

            setFaceImage(
                'cara_triste.png',
                'Conexión perdida'
            );

            break;

        // --------------------------
        // DEFAULT
        // --------------------------

        default:

            setFaceImage(
                'cara_feliz.png',
                'Patricio está feliz 😊'
            );
    }
}

// ==========================
// INDICADOR JUEGO
// ==========================

function updateGameIndicator() {

    const indicator = document.querySelector('.game-indicator');

    const icon = document.getElementById('game_icon');

    const text = document.getElementById('game_text');

    if (!indicator || !icon || !text) return;

    switch(currentGame) {

        // --------------------------
        // PILLA PILLA
        // --------------------------

        case 'pilla_pilla':

            indicator.style.display = 'flex';

            icon.style.display = 'block';

            icon.src = 'assets/faces/emoji_pilla_pilla.png';

            text.textContent = 'Jugando al Pilla-Pilla';

            break;

        // --------------------------
        // ESCONDITE
        // --------------------------

        case 'escondite':

            indicator.style.display = 'flex';

            icon.style.display = 'block';

            icon.src = 'assets/faces/emoji_escondite.png';

            text.textContent = 'Jugando al Escondite';

            break;

        // --------------------------
        // JUEGO DEL CALAMAR
        // --------------------------

        case 'calamar':

            indicator.style.display = 'flex';

            icon.style.display = 'block';

            icon.src = 'assets/faces/emoji_calamar.png';

            text.textContent = 'Jugando al Juego del Calamar';

            break;

        // --------------------------
        // DESCANSANDO
        // --------------------------

        default:

            indicator.style.display = 'flex';

            icon.style.display = 'none';

            text.textContent = 'Descansando';

            break;
    }
}

// ==========================
// ACTUALIZAR IMAGEN/TEXTO
// ==========================

function setFaceImage(imageName, emotionText) {

    const face = document.getElementById('robot_face');

    const text = document.getElementById('emotion_text');

    if (face) {

        face.src = `assets/faces/${imageName}`;
    }

    if (text) {

        text.textContent = emotionText;
    }
}

// ==========================
// DESCONECTADO
// ==========================

function setDisconnected() {

    currentEmotion = "disconnected";

    currentGame = "none";

    updateUI();
}

// ==========================
// START
// ==========================

window.onload = () => {

    connectROS();
};