# Resultado de detección de persona por frame
# Publicado en /patricio/vision/person_detection

std_msgs/Header header

bool detected              # ¿Se detectó una persona?

# Posición del centro del bounding box normalizado [0.0, 1.0]
float32 center_x           # 0.5 = centrado horizontalmente
float32 center_y           # 0.5 = centrado verticalmente

# Error respecto al centro del frame [-1.0, 1.0]
# 0.0 = perfectamente centrado
# Negativo = persona a la izquierda / arriba
float32 error_x
float32 error_y

# Tamaño del bounding box normalizado [0.0, 1.0]
float32 bbox_width
float32 bbox_height

# Confianza de la detección [0.0, 1.0]
float32 confidence

# Score de movimiento (solo relevante en fase LUZ_ROJA)
float32 movement_score