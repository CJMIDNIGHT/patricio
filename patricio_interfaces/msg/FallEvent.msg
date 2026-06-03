# FallEvent.msg — patricio_interfaces
# Publicado por fall_detection_node en /patricio/vision/fall_detected
# cuando se confirma una caída del niño.

# ── Cabecera estándar (timestamp + frame_id) ─────────────────────────────────
std_msgs/Header header

# ── Resultado de la detección ─────────────────────────────────────────────────
bool detected               # True si hay caída confirmada en este instante

# ── Score de criterios satisfechos (0–4) ─────────────────────────────────────
int32 criteria_score        # Cuántos de los 4 criterios se cumplen

# ── Métricas de pose en el momento de la caída ───────────────────────────────
float32 com_y               # Centro de masa Y normalizado (0=arriba, 1=abajo)
float32 torso_angle_deg     # Ángulo del torso respecto a la vertical (grados)
float32 bbox_ratio          # Relación anchura/altura del bounding box
float32 hip_y               # Altura media de las caderas normalizada
