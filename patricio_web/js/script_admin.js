let localIp = location.hostname;

let moveIntervalId = null;

// Publisher único y reutilizable para cmd_vel
let cmdVelTopic = null;

let data = {
    ros: null,
    rosbridge_address: `ws://${localIp}:9090`,
    connected: false,
    reverse: false,
    currentPosition: { x: 0, y: 0, z: 0, w: 1 }
};

// Velocidades según límites reales del TurtleBot3 Burger
const LINEAR_SPEED  = 0.22;   // m/s  (máx 0.22)
const ANGULAR_SPEED = 2.84;   // rad/s (máx 2.84)
const SPIN_SPEED    = 2.00;   // rad/s para rotación pura


// ─── Publicador central de cmd_vel ───────────────────────────────────────────

function getCmdVelTopic() {
    if (!data.connected) return null;
    if (!cmdVelTopic) {
        cmdVelTopic = new ROSLIB.Topic({
            ros: data.ros,
            name: '/cmd_vel',
            messageType: 'geometry_msgs/msg/Twist'
        });
    }
    return cmdVelTopic;
}

function publishTwist(linearX, angularZ) {
    const topic = getCmdVelTopic();
    if (!topic) {
        console.warn("No conectado, no se puede publicar en /cmd_vel");
        return;
    }
    const msg = new ROSLIB.Message({
        linear:  { x: linearX, y: 0, z: 0 },
        angular: { x: 0,       y: 0, z: angularZ }
    });
    topic.publish(msg);
    updateMonitorFeedback(linearX, angularZ);
}


// ─── Feedback en monitor ──────────────────────────────────────────────────────

function updateMonitorFeedback(linearX, angularZ) {
    const velSpan = document.getElementById("velocidad");
    const oriSpan = document.getElementById("orientacion_cmd");
    if (velSpan) velSpan.textContent = `${linearX.toFixed(2)} m/s`;
    if (oriSpan) oriSpan.textContent = `${angularZ.toFixed(2)} rad/s`;
}


// ─── Stop ─────────────────────────────────────────────────────────────────────

function stop() {
    publishTwist(0.0, 0.0);
    console.log("⏹ Robot detenido");
}


// ─── Movimiento WASD con mousedown / mouseup ──────────────────────────────────

let holdInterval = null;

function startMove(linearX, angularZ) {
    stopHold();
    publishTwist(linearX, angularZ);
    holdInterval = setInterval(() => publishTwist(linearX, angularZ), 50);
}

function stopHold() {
    if (holdInterval) {
        clearInterval(holdInterval);
        holdInterval = null;
    }
}

function bindMoveButton(id, linearX, angularZ) {
    const btn = document.getElementById(id);
    if (!btn) return;

    btn.addEventListener("mousedown",  () => startMove(linearX, angularZ));
    btn.addEventListener("mouseup",    () => { stopHold(); stop(); });
    btn.addEventListener("mouseleave", () => { stopHold(); stop(); });

    // Soporte táctil (móvil / tablet)
    btn.addEventListener("touchstart", (e) => { e.preventDefault(); startMove(linearX, angularZ); });
    btn.addEventListener("touchend",   (e) => { e.preventDefault(); stopHold(); stop(); });
}

// ─── moveRobot (click puntual, se mantiene por compatibilidad) ────────────────

function moveRobot(direccion) {
    if (!data.connected) {
        console.warn("No conectado, no se puede mover");
        return;
    }
    switch (direccion) {
        case "delante":    publishTwist( LINEAR_SPEED,  0.0);           break;
        case "atras":      publishTwist(-LINEAR_SPEED,  0.0);           break;
        case "izquierda":  publishTwist( 0.0,           ANGULAR_SPEED); break;
        case "derecha":    publishTwist( 0.0,          -ANGULAR_SPEED); break;
    }
    console.log(`Moviendo: ${direccion}`);
}


// ─── Cancelar navegación ──────────────────────────────────────────────────────

function cancelNavigation() {
    if (moveIntervalId) {
        clearInterval(moveIntervalId);
        moveIntervalId = null;
        console.log("Movimiento manual cancelado");
    }

    stop();

    const x = parseFloat(document.getElementById("pos_x").innerText);
    const y = parseFloat(document.getElementById("pos_y").innerText);
    const w = parseFloat(document.getElementById("pos_w").innerText);

    if (!isNaN(x) && !isNaN(y) && !isNaN(w)) {
        sendNavGoal(x, y, w);
        console.log(`Navegación cancelada reenviando objetivo a (${x.toFixed(2)}, ${y.toFixed(2)}, ${w.toFixed(2)})`);
    } else {
        console.warn("Coordenadas actuales inválidas, no se puede cancelar la navegación.");
    }
}


// ─── Enviar objetivo de navegación ───────────────────────────────────────────

let navGoalClient = null;

function sendNavGoal(x, y, w = 1.0) {
    if (!data.connected) {
        console.warn("No conectado");
        return;
    }

    const goalPublisher = new ROSLIB.Topic({
        ros: data.ros,
        name: '/goal_pose',
        messageType: 'geometry_msgs/msg/PoseStamped'
    });

    const goal = new ROSLIB.Message({
        header: { frame_id: "map" },
        pose: {
            position:    { x: x, y: y, z: 0.0 },
            orientation: { x: 0.0, y: 0.0, z: 0.0, w: w }
        }
    });

    console.log("Enviando objetivo a /goal_pose:", goal);
    goalPublisher.publish(goal);
}


// ─── Dirección IP ─────────────────────────────────────────────────────────────

function updateRosBridgeAddress() {
    const ipInput = document.getElementById("ipInput");
    if (ipInput) {
        data.rosbridge_address = ipInput.value || data.rosbridge_address;
    }
}


// ─── navigateTo (navegación manual por cmd_vel) ───────────────────────────────

function navigateTo(targetX, targetY, targetOrientationW = 1.0) {
    if (!data.connected) { console.warn("No conectado"); return; }

    function rotateToTargetOrientation() {
        const error = targetOrientationW - data.currentPosition.w;
        if (Math.abs(error) > 0.02) {
            publishTwist(0, error > 0 ? 0.8 : -0.8);
            setTimeout(rotateToTargetOrientation, 100);
        } else {
            stop();
            moveToTarget();
        }
    }

    function moveToTarget() {
        moveIntervalId = setInterval(() => {
            const dist = Math.sqrt(
                Math.pow(targetX - data.currentPosition.x, 2) +
                Math.pow(targetY - data.currentPosition.y, 2)
            );
            if (dist > 0.7) {
                publishTwist(0.5, 0);
            } else {
                clearInterval(moveIntervalId);
                moveIntervalId = null;
                stop();
            }
        }, 1000);
    }

    rotateToTargetOrientation();
}

 // Función para activar el stream de la cámara (Santiago Aguirre)
function activarCamara() {
    const img = document.getElementById("cameraFeed");
    if (!img) return;
    img.src = `http://${localIp}:8080/stream?topic=/patricio/camera_processed&timestamp=${Date.now()}`;
    console.log("📷 Stream de cámara activado:", img.src);
}

// ─── Conexión ─────────────────────────────────────────────────────────────────

function connect() {
    console.log("Clic en connect");

    console.log("Activando cámara...");
    activarCamara()

    updateRosBridgeAddress();
    cmdVelTopic = null; // reset al reconectar

    data.ros = new ROSLIB.Ros({ url: data.rosbridge_address });

    data.ros.on("connection", () => {
        data.connected = true;
        cmdVelTopic = null;
        initGameTopics(data.ros);  // defined in ros_logic.js — also inits calamar topics
        document.getElementById("estado").textContent = '🔌 Conectado';
        document.getElementById("estado").style.color = 'green';
        console.log("Conexión con ROSBridge correcta");;

        // ── Mapa ──────────────────────────────────────────────────────────────
        const canvas  = document.getElementById("mapCanvas");
        const ctx     = canvas.getContext("2d");
        const image   = new Image();
        let   mapInfo = null;

        image.onload = () => {
            canvas.width  = image.width;
            canvas.height = image.height;
            ctx.drawImage(image, 0, 0);
        };
        image.onerror = () => console.error("Error al cargar imagen del mapa:", image.src);

        image.onerror = () => {
            console.error("Error al cargar la imagen:", image.src);
        };

        // 加载 YAML 并设置图片路径 Cargar YAML y establecer la ruta de la imagen
        /*fetch(`http://${localIp}:8000/static/farmaciaMapa.yaml`)

            .then(res => res.text())
            .then(text => {
                mapInfo = jsyaml.load(text);
                image.src = `http://${localIp}:8000/static/` + mapInfo.image;

            });*/

        // ── /odom ─────────────────────────────────────────────────────────────
        const odomTopic = new ROSLIB.Topic({
            ros: data.ros,
            name: '/odom',
            messageType: 'nav_msgs/msg/Odometry'
        });

        odomTopic.subscribe((message) => {
            const position    = message.pose.pose.position;
            const orientation = message.pose.pose.orientation;

            data.currentPosition = {
                x: position.x,
                y: position.y,
                z: position.z,
                w: orientation.w
            };

            document.getElementById("pos_x").textContent = position.x.toFixed(2);
            document.getElementById("pos_y").textContent = position.y.toFixed(2);
            document.getElementById("pos_w").textContent = orientation.w.toFixed(2);

            // Orientación en monitor
            const oriSpan = document.getElementById("orientacion_cmd");
            if (oriSpan) oriSpan.textContent = `${orientation.w.toFixed(3)} w`;

            if (!mapInfo || !image.complete) return;

            const res    = mapInfo.resolution;
            const origin = mapInfo.origin;
            const pixelX = (position.x - origin[0]) / res;
            const pixelY = canvas.height - ((position.y - origin[1]) / res);

            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.drawImage(image, 0, 0);
            ctx.beginPath();
            ctx.fillStyle = "green";
            ctx.arc(pixelX, pixelY, 5, 0, 2 * Math.PI);
            ctx.fill();
        });

        // ── Temperatura ───────────────────────────────────────────────────────
        const temperaturaSpan = document.getElementById("temperatura");
        if (temperaturaSpan) {
            const tempTopic = new ROSLIB.Topic({
                ros: data.ros,
                name: '/temperature',
                messageType: 'sensor_msgs/msg/Temperature'
            });
            tempTopic.subscribe((message) => {
                temperaturaSpan.textContent = `🌡 Temperatura: ${message.temperature.toFixed(1)} °C`;
            });
        }
    });

    data.ros.on("error", (error) => {
        console.error("Error de conexión:", error);
        document.getElementById("estado").textContent = 'Error de conexión';
        document.getElementById("estado").style.color = 'red';
    });

    data.ros.on("close", () => {
        data.connected = false;
        cmdVelTopic = null;
        document.getElementById("estado").textContent = 'Desconectado';
        document.getElementById("estado").style.color = 'red';
        console.log("Conexión cerrada");
    });
}


// ─── Desconexión ──────────────────────────────────────────────────────────────

function disconnect() {
    if (data.ros) {
        data.ros.close();
        data.connected = false;
        cmdVelTopic = null;
        document.getElementById("estado").textContent = '🔌 Desconectado';
        document.getElementById("estado").style.color = 'red';
        console.log("Clic en desconectar");
    }
}


// ─── Movimiento circular (btn_move / btn_reverse) ────────────────────────────

function move() {
    if (!data.connected) { console.warn("No conectado"); return; }
    publishTwist(0.1, data.reverse ? 0.2 : -0.2);
}

function reverse() {
    data.reverse = !data.reverse;
    console.log("Dirección cambiada:", data.reverse ? "Adelante" : "Atrás");
}


// ─── Rutas predefinidas ───────────────────────────────────────────────────────

function moveCasaToColaClientes() {
    if (!data.connected) { console.warn("No conectado"); return; }
    const targetOrientationW = -0.70, targetX = 4.5, targetY = 7.5;
    function rotateToTargetOrientation() {
        const error = targetOrientationW - data.currentPosition.w;
        if (Math.abs(error) > 0.01) {
            publishTwist(0, error > 0 ? 0.8 : -0.8);
            setTimeout(rotateToTargetOrientation, 100);
        } else { stop(); moveToTarget(); }
    }
    function moveToTarget() {
        moveIntervalId = setInterval(() => {
            const dist = Math.sqrt(Math.pow(targetX - data.currentPosition.x, 2) + Math.pow(targetY - data.currentPosition.y, 2));
            if (dist > 0.7) {
                publishTwist(targetY > data.currentPosition.y ? 0.5 : -0.3, 0);
            } else { clearInterval(moveIntervalId); moveIntervalId = null; stop(); }
        }, 1000);
    }
    rotateToTargetOrientation();
}

function moveCasaToAlmacen() {
    if (!data.connected) { console.warn("No conectado"); return; }
    const targetOrientationW = 0.48, targetX = 2.76, targetY = -10.76;
    function rotateToTargetOrientation() {
        const error = targetOrientationW - data.currentPosition.w;
        if (Math.abs(error) > 0.02) {
            publishTwist(0, error > 0 ? 0.8 : -0.8);
            setTimeout(rotateToTargetOrientation, 100);
        } else { stop(); moveToTarget(); }
    }
    function moveToTarget() {
        moveIntervalId = setInterval(() => {
            const dist = Math.sqrt(Math.pow(targetX - data.currentPosition.x, 2) + Math.pow(targetY - data.currentPosition.y, 2));
            if (dist > 0.7) {
                publishTwist(targetY > data.currentPosition.y ? -0.5 : 0.3, 0);
            } else { clearInterval(moveIntervalId); moveIntervalId = null; stop(); }
        }, 1000);
    }
    rotateToTargetOrientation();
}

function moveColaClientesToAlmacen() {
    if (!data.connected) { console.warn("No conectado"); return; }
    const targetOrientationW = 0.70, targetX = 4.5, targetY = -8;
    function rotateToTargetOrientation() {
        const error = targetOrientationW - data.currentPosition.w;
        if (Math.abs(error) > 0.02) {
            publishTwist(0, error > 0 ? 0.8 : -0.8);
            setTimeout(rotateToTargetOrientation, 100);
        } else { stop(); moveToTarget(); }
    }
    function moveToTarget() {
        moveIntervalId = setInterval(() => {
            const dist = Math.sqrt(Math.pow(targetX - data.currentPosition.x, 2) + Math.pow(targetY - data.currentPosition.y, 2));
            if (dist > 0.7) {
                publishTwist(targetY > data.currentPosition.y ? -0.5 : 0.3, 0);
            } else { clearInterval(moveIntervalId); moveIntervalId = null; moveCasaToAlmacen(); stop(); }
        }, 1000);
    }
    rotateToTargetOrientation();
}

function moveColaClientesToCasa() {
    if (!data.connected) { console.warn("No conectado"); return; }
    const targetOrientationW = 0.70, targetX = 4.5, targetY = -8;
    function rotateToTargetOrientation() {
        const error = targetOrientationW - data.currentPosition.w;
        if (Math.abs(error) > 0.02) {
            publishTwist(0, error > 0 ? 0.8 : -0.8);
            setTimeout(rotateToTargetOrientation, 100);
        } else { stop(); moveToTarget(); }
    }
    function moveToTarget() {
        moveIntervalId = setInterval(() => {
            const dist = Math.sqrt(Math.pow(targetX - data.currentPosition.x, 2) + Math.pow(targetY - data.currentPosition.y, 2));
            if (dist > 0.7) {
                publishTwist(targetY > data.currentPosition.y ? -0.5 : 0.3, 0);
            } else { clearInterval(moveIntervalId); moveIntervalId = null; stop(); }
        }, 1000);
    }
    rotateToTargetOrientation();
}

function moveAlmacenToColaClientes() {
    if (!data.connected) { console.warn("No conectado"); return; }
    const targetOrientationW = -0.94, targetX = 4, targetY = -8.5;
    function rotateToTargetOrientation() {
        const error = targetOrientationW - data.currentPosition.w;
        if (Math.abs(error) > 0.02) {
            publishTwist(0, -0.8);
            setTimeout(rotateToTargetOrientation, 100);
        } else { stop(); moveToTarget(); }
    }
    function moveToTarget() {
        moveIntervalId = setInterval(() => {
            const dist = Math.sqrt(Math.pow(targetX - data.currentPosition.x, 2) + Math.pow(targetY - data.currentPosition.y, 2));
            if (dist > 0.7) {
                publishTwist(targetY > data.currentPosition.y ? 0.5 : -0.3, 0);
            } else { clearInterval(moveIntervalId); moveIntervalId = null; moveCasaToColaClientes(); stop(); }
        }, 1000);
    }
    rotateToTargetOrientation();
}

function moveAlmacenToCasa() {
    if (!data.connected) { console.warn("No conectado"); return; }
    const targetOrientationW = -0.94, targetX = 4.5, targetY = -8;
    function rotateToTargetOrientation() {
        const error = targetOrientationW - data.currentPosition.w;
        if (Math.abs(error) > 0.02) {
            publishTwist(0, -0.8);
            setTimeout(rotateToTargetOrientation, 100);
        } else { stop(); moveToTarget(); }
    }
    function moveToTarget() {
        moveIntervalId = setInterval(() => {
            const dist = Math.sqrt(Math.pow(targetX - data.currentPosition.x, 2) + Math.pow(targetY - data.currentPosition.y, 2));
            if (dist > 0.7) {
                publishTwist(targetY > data.currentPosition.y ? 0.5 : -0.3, 0);
            } else { clearInterval(moveIntervalId); moveIntervalId = null; stop(); }
        }, 1000);
    }
    rotateToTargetOrientation();
}


/*function updateCameraFeed() {
// ─── Cámara ───────────────────────────────────────────────────────────────────
    const img = document.getElementById("cameraFeed");
    const timestamp = new Date().getTime(); // Evitar el almacenamiento en caché
    img.src = `http://${localIp}:8080/stream?topic=/image&timestamp=${timestamp}`;
  }
  
  
  // 每隔 2 秒刷新一次图像--Actualizar la imagen cada 2 segundos
  setInterval(updateCameraFeed, 2000);*/

document.addEventListener('DOMContentLoaded', event => {
    
    // 自动根据页面地址设置 IP     Establecer IP automáticamente según la dirección de la página
    document.getElementById("ipInput").value = `ws://${localIp}:9090`;
    
    /*const timestamp = new Date().getTime(); 
    document.getElementById("cameraFeed").src = `http://${localIp}:8080/stream?topic=/image&timestamp=${timestamp}`;*/
    
    document.getElementById("btn_goto_cola").addEventListener("click", () => {
        sendNavGoal(3.998915, 4.900286, 1.0);
    });
    document.getElementById("btn_goto_casa").addEventListener("click", () => {
        sendNavGoal(4.500114, -8.000002, 1.0);
    });
    document.getElementById("btn_goto_almacen").addEventListener("click", () => {
        sendNavGoal(0.009239, -15.876596, 1.0);
    });
    

    // Conexión
    document.getElementById("btn_con").addEventListener("click", connect);
    document.getElementById("btn_dis").addEventListener("click", disconnect);

    // Movimiento circular
    document.getElementById("btn_move").addEventListener("click", move);
    document.getElementById("btn_stop").addEventListener("click", stop);
    document.getElementById("btn_reverse").addEventListener("click", reverse);

    // WASD
    bindMoveButton("btn_wsad_delante",   LINEAR_SPEED,  0.0);
    bindMoveButton("btn_wsad_atras",    -LINEAR_SPEED,  0.0);
    bindMoveButton("btn_wsad_izquierda", 0.0,           ANGULAR_SPEED);
    bindMoveButton("btn_wsad_derecha",   0.0,          -ANGULAR_SPEED);

    document.getElementById("btn_wsad_parar").addEventListener("click", stop);

    // Spin
    bindMoveButton("btn_spin_left",  0.0,  SPIN_SPEED);
    bindMoveButton("btn_spin_right", 0.0, -SPIN_SPEED);

    // Navegación predefinida
    document.getElementById("btn_goto_cola").addEventListener("click",    () => sendNavGoal(3.998915,  4.900286,  1.0));
    document.getElementById("btn_goto_casa").addEventListener("click",    () => sendNavGoal(4.500114, -8.000002,  1.0));
    document.getElementById("btn_goto_almacen").addEventListener("click", () => sendNavGoal(0.009239, -15.876596, 1.0));
    document.getElementById("btn_cancelar_nav").addEventListener("click", cancelNavigation);

    // Juegos — pilla_pilla y escondite (ros_logic.js)
    document.getElementById('btn_pilla_pilla').addEventListener('click', () => iniciarJuego('pilla_pilla'));
    document.getElementById('btn_escondite').addEventListener('click',   () => iniciarJuego('escondite'));
    document.getElementById('btn_stop_juego').addEventListener('click',  detenerJuego);

    // Juego del Calamar — funciones definidas en ros_logic.js
    document.getElementById('btn_calamar_auto').addEventListener('click', () => { iniciarCalamarAuto(); window.open('calamar_game.html', '_blank'); });
    document.getElementById('btn_luz_verde').addEventListener('click',    calamarLuzVerde);
    document.getElementById('btn_luz_roja').addEventListener('click',     calamarLuzRoja);

    // Mostrar controles manuales del calamar al conectar
    const calamarControls = document.getElementById('calamar_manual_controls');
    if (calamarControls) calamarControls.style.display = 'none';

    console.log("Página admin cargada");
});


// ─── Captura de imagen ────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", function () {
    const btnGuardar  = document.getElementById("btn_guardar_imagen");
    const cameraFeed  = document.getElementById("cameraFeed");
    const idSpan      = document.getElementById("patricio-ultimo-id");

    if (!btnGuardar || !cameraFeed) return;

    btnGuardar.addEventListener("click", function () {
        const canvas = document.createElement("canvas");
        canvas.width = cameraFeed.videoWidth || 640;
        canvas.height = cameraFeed.videoHeight || 480;

        canvas.toBlob(function (blob) {
            if (blob) {
                const url = URL.createObjectURL(blob);
                const a   = document.createElement("a");
                a.href     = url;
                a.download = "robot_camera.jpg";
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            } else {
                alert("No se pudo capturar la imagen.");
            }
        }, "image/jpeg");
    });

    if (typeof data !== 'undefined' && data.ros) {
        const ultimoSipTopic = new ROSLIB.Topic({
            ros: data.ros,
            name: '/ultimo_sip',
            messageType: 'std_msgs/msg/String'
        });
        ultimoSipTopic.subscribe(function (message) {
            if (idSpan) idSpan.textContent = message.data;
        });
    }
});