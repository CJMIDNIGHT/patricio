-- =====================================================================
-- PATRICIO — importación completa (base de datos + tablas + datos demo)
-- =====================================================================
--
--   sudo mysql < patricio_import_completo.sql
--
-- Crea: patricio_db, usuario MySQL patricio@localhost (clave Patricio_local1!),
--       tablas users, actividades, partidas, incidencias
-- Usuarios demo — contraseña de login en la app: 1234
--
-- =====================================================================

SET NAMES utf8mb4;

CREATE DATABASE IF NOT EXISTS patricio_db
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'patricio'@'localhost' IDENTIFIED BY 'Patricio_local1!';
GRANT ALL PRIVILEGES ON patricio_db.* TO 'patricio'@'localhost';
FLUSH PRIVILEGES;

USE patricio_db;

-- ── Tablas (esquema ER) ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS users (
    id_usuario  INT UNSIGNED NOT NULL AUTO_INCREMENT,
    nombre      VARCHAR(20) NOT NULL,
    apellidos   VARCHAR(40) NOT NULL,
    email       VARCHAR(255) NOT NULL,
    dni         VARCHAR(9) NULL,
    direccion   VARCHAR(255) NULL,
    telefono    VARCHAR(20) NULL,
    contrasenya VARCHAR(255) NOT NULL COMMENT 'hash bcrypt',
    PRIMARY KEY (id_usuario),
    UNIQUE KEY uq_users_email (email),
    UNIQUE KEY uq_users_dni (dni),
    KEY ix_users_nombre (nombre)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS actividades (
    id_actividad INT UNSIGNED NOT NULL AUTO_INCREMENT,
    nombre       VARCHAR(100) NOT NULL,
    tipo         VARCHAR(50) NOT NULL,
    PRIMARY KEY (id_actividad),
    UNIQUE KEY uq_actividades_nombre (nombre),
    KEY ix_actividades_tipo (tipo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS partidas (
    id_partida    BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    id_usuario    INT UNSIGNED NULL,
    id_actividad  INT UNSIGNED NOT NULL,
    puntuacion    FLOAT NULL,
    duracion      INT NOT NULL DEFAULT 0,
    detalles_json JSON NULL,
    fecha         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id_partida),
    KEY ix_partidas_usuario (id_usuario),
    KEY ix_partidas_actividad (id_actividad),
    KEY ix_partidas_fecha (fecha),
    CONSTRAINT fk_partidas_usuario
        FOREIGN KEY (id_usuario) REFERENCES users(id_usuario)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_partidas_actividad
        FOREIGN KEY (id_actividad) REFERENCES actividades(id_actividad)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS incidencias (
    id_incidencia INT UNSIGNED NOT NULL AUTO_INCREMENT,
    tipo          VARCHAR(50) NOT NULL,
    descripcion   VARCHAR(255) NOT NULL,
    fecha         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resuelto      TINYINT(1) NOT NULL DEFAULT 0,
    id_usuario    INT UNSIGNED NULL,
    PRIMARY KEY (id_incidencia),
    KEY ix_incidencias_usuario (id_usuario),
    KEY ix_incidencias_tipo (tipo),
    KEY ix_incidencias_resuelto (resuelto),
    KEY ix_incidencias_fecha (fecha),
    CONSTRAINT fk_incidencias_usuario
        FOREIGN KEY (id_usuario) REFERENCES users(id_usuario)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── Actividades (juegos Patricio) ─────────────────────────────────────

INSERT INTO actividades (nombre, tipo) VALUES
  ('Pilla-Pilla', 'juego'),
  ('Escondite', 'juego'),
  ('Juego del Calamar', 'juego')
ON DUPLICATE KEY UPDATE tipo = VALUES(tipo);

-- ── Usuarios demo (contraseña app: 1234) ──────────────────────────────

INSERT INTO users (nombre, apellidos, email, contrasenya)
VALUES
  ('Admin',    'Sistema',   'admin@patricio.local',
   '$2b$12$b9Y1u6yufc/DY.a7aEMacOvzrB/kj61K95mLkZ21ECAPrqQL.L6de'),
  ('Educador', 'Demo',      'educador@patricio.local',
   '$2b$12$b9Y1u6yufc/DY.a7aEMacOvzrB/kj61K95mLkZ21ECAPrqQL.L6de'),
  ('Familia',  'Demo',      'familia@patricio.local',
   '$2b$12$b9Y1u6yufc/DY.a7aEMacOvzrB/kj61K95mLkZ21ECAPrqQL.L6de')
ON DUPLICATE KEY UPDATE
  contrasenya = VALUES(contrasenya),
  nombre      = VALUES(nombre),
  apellidos   = VALUES(apellidos);
