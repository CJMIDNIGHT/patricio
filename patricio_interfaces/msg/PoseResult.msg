# Resultado completo de MediaPipe Pose
# Publicado en /patricio/vision/pose_landmarks

std_msgs/Header header

bool detected              # ¿Hay landmarks disponibles?

# 33 landmarks de MediaPipe Pose, coordenadas normalizadas [0.0, 1.0]
# Índices: https://developers.google.com/mediapipe/solutions/vision/pose_landmarker
float32[] landmarks_x      # longitud 33
float32[] landmarks_y      # longitud 33
float32[] landmarks_z      # longitud 33 (profundidad relativa)
float32[] landmarks_visibility  # longitud 33

# Score de movimiento entre frame actual y anterior
# Calculado sobre landmarks [0, 11-16, 23-28]
float32 movement_score

# Frame de referencia del movimiento
# 0.0 = sin movimiento, >0.015 = movimiento significativo
float32 movement_threshold_used