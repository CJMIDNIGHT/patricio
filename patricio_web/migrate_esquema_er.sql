-- Migración: esquema antiguo → esquema ER (users, actividades, partidas, incidencias)
-- ADVERTENCIA: elimina tablas antiguas y todos sus datos. Hacer copia de seguridad antes.
--
--   mysqldump -u patricio -p patricio_db > backup_antes_migracion.sql
--   mysql -u patricio -p patricio_db < migrate_esquema_er.sql
--   mysql -u patricio -p patricio_db < schema.sql
--   mysql -u patricio -p patricio_db < seed_usuarios_prueba.sql

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS historico_juegos;
DROP TABLE IF EXISTS partidas;
DROP TABLE IF EXISTS incidencias;
DROP TABLE IF EXISTS actividades;
DROP TABLE IF EXISTS usuario;
DROP TABLE IF EXISTS users;

SET FOREIGN_KEY_CHECKS = 1;
