-- Usuarios de prueba: contraseña `1234` para todos (hash bcrypt).
-- Importar tras schema.sql o patricio_import_completo.sql:
--   mysql -u patricio -p patricio_db < seed_usuarios_prueba.sql

SET NAMES utf8mb4;

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

INSERT INTO actividades (nombre, tipo) VALUES
  ('Pilla-Pilla', 'juego'),
  ('Escondite', 'juego'),
  ('Juego del Calamar', 'juego')
ON DUPLICATE KEY UPDATE tipo = VALUES(tipo);
