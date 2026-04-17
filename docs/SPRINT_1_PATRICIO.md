# Proyecto de robótica — Patricio

**SPRINT 1**  
**Equipo 7**

**Documento técnico** (estructura referencia PAMABOT)  
*Versión borrador basada en el repositorio actual*

**Autores (README del repositorio):**  
Adenor Buret, Santiago Aguirre Crespo, Pablo Meana, Mari Dapcheva, César Herrero, Juan Bautista  

---

## Índice

1. [Concepción del producto](#1-concepción-del-producto)  
2. [Patricio](#2-patricio)  
3. [Paquetes utilizados](#3-paquetes-utilizados)  
   - 3.1 [patricio (metapaquete)](#31-patricio-metapaquete)  
   - 3.2 [patricio_my_world](#32-patricio_my_world)  
   - 3.3 [patricio_captacion](#33-patricio_captacion)  
   - 3.4 [patricio_nav_punto](#34-patricio_nav_punto)  
   - 3.5 [patricio_nav_ruta](#35-patricio_nav_ruta)  
4. [Entorno simulado y topics principales](#4-entorno-simulado-y-topics-principales)  
5. [Mapa y navegación](#5-mapa-y-navegación)  
6. [Base de datos](#6-base-de-datos)  
7. [Nodos y ejecución](#7-nodos-y-ejecución)  
8. [Sostenibilidad y escalabilidad](#8-sostenibilidad-y-escalabilidad)  
9. [Conclusión](#9-conclusión)  

---

## 1. Concepción del producto

Durante la fase de concepción se definió **Patricio** como un **robot educativo** orientado a niños de **4 a 6 años**, con el objetivo de fomentar el aprendizaje mediante interacción lúdica e integración de inteligencia artificial para una experiencia autónoma y adaptativa.

La propuesta se apoya en:

- Un **público objetivo** claro (educación infantil temprana).  
- **Funcionalidades previstas** descritas en el README del proyecto: matemáticas y alfabeto, narración de cuentos y chistes, juegos de movimiento (“pilla pilla”, “el pollito inglés”), baile y canto, expresión en pantalla, navegación autónoma, reconocimiento de voz y detección de impactos.  
- Una base técnica sobre **ROS 2**, simulación y módulos de navegación y captación sensorial.

*Nota: parte de estas funcionalidades está descrita a nivel de diseño; el grado de implementación en código varía según el paquete.*

---

## 2. Patricio

Patricio es un proyecto que combina **robótica educativa** y **software modular** en ROS 2. El foco está en el **aprendizaje**, la **accesibilidad** para niños pequeños y la **extensibilidad** del sistema (simulación, navegación, percepción).

El repositorio organiza el trabajo en un **metapaquete** `patricio` y varios paquetes especializados (`patricio_my_world`, `patricio_captacion`, `patricio_nav_punto`, `patricio_nav_ruta`).

---

## 3. Paquetes utilizados

### 3.1 `patricio` (metapaquete)

**Descripción:** paquete CMake que agrupa dependencias de alto nivel del proyecto (versión indicada en `package.xml`: 2.1.4).

**Estructura (resumen):**

```
patricio/
├── CMakeLists.txt
└── package.xml
```

**Nota:** En `package.xml` aparece la dependencia de ejecución `patricio_mundo`; en el workspace actual el paquete de simulación se llama **`patricio_my_world`**. Conviene unificar el nombre para que `rosdep` y los lanzamientos globales no fallen.

**Nodos:** no define ejecutables propios; es un contenedor de metadatos y dependencias.

---

### 3.2 `patricio_my_world`

**Descripción:** simulación en **Gazebo Sim (gz)** con mundo personalizado, modelos TurtleBot3 (p. ej. `turtlebot3_burger`), puentes ROS–Gazebo y utilidades en C++.

**Estructura (resumen):**

```
patricio_my_world/
├── CMakeLists.txt
├── package.xml
├── launch/
│   ├── house.launch.py
│   ├── robot_state_publisher.launch.py
│   └── spawn_turtlebot3.launch.py
├── worlds/
│   └── house.sdf
├── models/
│   ├── turtlebot3_burger/
│   ├── turtlebot3_burger_cam/
│   └── turtlebot3_common/
├── params/
│   ├── turtlebot3_burger_bridge.yaml
│   └── turtlebot3_burger_cam_bridge.yaml
├── urdf/
├── rviz/
├── include/
└── src/
    ├── turtlebot3_drive.cpp
    ├── obstacles.cpp
    ├── obstacle1.cpp
    └── obstacle2.cpp
```

**Lanzamiento principal:** `house.launch.py` carga el mundo `house.sdf`, arranca gz (servidor y cliente), `robot_state_publisher`, y el *spawn* del TurtleBot3 con `ros_gz_sim` / `ros_gz_bridge` según el modelo definido por `TURTLEBOT3_MODEL`.

**Plugins y binarios compilados:**

- `turtlebot3_drive`: nodo ROS 2 que publica en `cmd_vel` y se suscribe a `scan` y `odom` (comportamiento tipo evitación / telemetría según la lógica del `.cpp`).  
- Bibliotecas compartidas `obstacles`, `obstacle1`, `obstacle2`: plugins de simulación (entorno dinámico / obstáculos).

**Topics relevantes (vía puente `*_bridge.yaml`):**

| Topic (ROS)   | Rol típico |
|---------------|------------|
| `/clock`      | Tiempo de simulación |
| `/joint_states` | Estados articulares |
| `/odom`       | Odometría |
| `/tf`         | Transformadas |
| `/cmd_vel`    | Comando de velocidad (ROS → Gazebo) |
| `/imu`        | IMU |
| `/scan`       | Láser 2D |

**Servicios / acciones propias del paquete:** no se documentan acciones personalizadas en este paquete; la interacción principal es por topics estándar y el lanzamiento de gz.

---

### 3.3 `patricio_captacion`

**Descripción (prevista en README):** módulo de **captura sensorial y percepción**.

**Estado en el repositorio:** paquete **ament_python** con `setup.py` y `package.xml`; **no hay módulos Python** ni `console_scripts` registrados todavía — estructura preparada para desarrollo futuro.

**Dependencias declaradas en `package.xml`:** `rclpy`, `geometry_msgs`, `std_msgs`, `nav_msg` (revisar coherencia con el nombre estándar `nav_msgs` en ROS 2).

---

### 3.4 `patricio_nav_punto`

**Descripción (prevista en README):** navegación hacia **puntos concretos**.

**Estado en el repositorio:** esqueleto de paquete Python **sin nodos publicados** en `entry_points`.

**Dependencias declaradas:** análogas a `patricio_captacion`.

---

### 3.5 `patricio_nav_ruta`

**Descripción (prevista en README):** **planificación y seguimiento de rutas**.

**Estado en el repositorio:** esqueleto de paquete Python **sin nodos** en `setup.py`.

---

## 4. Entorno simulado y topics principales

El mundo **`house.sdf`** define un entorno interior con suelo, muros y elementos estáticos; está pensado para pruebas de navegación y percepción láser en simulación.

En ejecución con `house.launch.py` y el *spawn* del robot:

- El **láser** publica típicamente en `/scan` (puente).  
- La **odometría** en `/odom`.  
- Los **comandos de movimiento** se envían a `/cmd_vel` (coherente con el tipo que defina el puente y los publicadores del equipo).

---

## 5. Mapa y navegación

El entorno principal de prueba en esta fase es el **mundo SDF** (`house.sdf`). La integración con **Nav2**, mapa ocupacional (`.yaml` / `.pgm`) y parámetros de navegación **se añadirá en una fase posterior** del proyecto.

---

## 6. Base de datos

*(Sección reservada para edición posterior: diseño de la base de datos del sistema Patricio — entidades, relaciones y uso previsto en el contexto educativo.)*

---

## 7. Nodos y ejecución

**Nodos / procesos identificados:**

| Componente | Paquete | Función breve |
|------------|---------|----------------|
| Gazebo Sim (`gz sim`) | `ros_gz_sim` | Simulación física y visual |
| `parameter_bridge` | `ros_gz_bridge` | Sincronización de topics ROS ↔ gz |
| `create` (spawn) | `ros_gz_sim` | Inserta el modelo del robot |
| `robot_state_publisher` | `robot_state_publisher` | Publica el modelo según URDF |
| `turtlebot3_drive` | `patricio_my_world` | Nodo C++ de conducción / reacción a láser y odometría |

**Comando típico de simulación:**

```bash
# Desde el workspace compilado, con TURTLEBOT3_MODEL=burger (u otro) exportado
ros2 launch patricio_my_world house.launch.py
```

En el futuro se prevé un lanzamiento unificado `patricio.launch.py` en el metapaquete `patricio` para orquestar el sistema completo.

---

## 8. Sostenibilidad y escalabilidad

- **Modularidad:** separación entre simulación (`patricio_my_world`), captación y navegación facilita iterar por subsistemas.  
- **Educación:** el proyecto apunta a un impacto social positivo (aprendizaje infantil) sin depender de un único entorno físico si la simulación y los mapas se mantienen actualizados.  
- **Escalado software:** completar mensajes estándar o interfaces propias, tests y lanzamientos unificados reduce deuda técnica antes de añadir IA o voz.

---

## 9. Conclusión

Patricio es un proyecto de **robótica educativa** con una visión clara de producto (README) y una base de **simulación funcional** en `patricio_my_world` (Gazebo Sim, TurtleBot3, puentes, nodo `turtlebot3_drive`). Los paquetes `patricio_captacion`, `patricio_nav_punto` y `patricio_nav_ruta` están **en fase de estructura** y deben completarse para alinear el código con las funcionalidades anunciadas (navegación y captación). La **base de datos** y el **mapa/nav2** se desarrollarán en iteraciones posteriores.

Este documento puede exportarse a PDF desde el editor o con herramientas tipo `pandoc` cuando el equipo cierre el contenido pedagógico.

---

*Documento técnico — SPRINT 1 — Equipo 7 — estado del repositorio `patricio`.*
