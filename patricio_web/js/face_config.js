/**
 * Configuración de rosbridge para la pantalla física (Raspberry Pi + LCD).
 *
 * Prioridad de la IP del robot:
 *   1. ?ros_host=192.168.x.x en la URL
 *   2. localStorage patricio_ros_host (guardado desde consola o instalador)
 *   3. variable global window.PATRICIO_ROS_HOST (inyectada antes de cargar)
 *   4. hostname de la propia página (rosbridge en la misma Raspberry)
 */
(function (global) {
  const params = new URLSearchParams(global.location.search);
  const host =
    params.get('ros_host') ||
    params.get('ros') ||
    global.PATRICIO_ROS_HOST ||
    global.localStorage.getItem('patricio_ros_host') ||
    global.location.hostname;
  const port =
    params.get('ros_port') ||
    global.PATRICIO_ROS_PORT ||
    global.localStorage.getItem('patricio_ros_port') ||
    '9090';
  global.PATRICIO_ROSBRIDGE_URL = `ws://${host}:${port}`;
})(window);
