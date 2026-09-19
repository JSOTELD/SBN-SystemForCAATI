-- Sistema de Gestión de Activos TI
-- Ejecutar desde phpMyAdmin o desde la consola de MariaDB/MySQL.

CREATE DATABASE IF NOT EXISTS itam_sbn
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE itam_sbn;

-- La estructura de tablas es administrada por SQLAlchemy para mantenerla
-- sincronizada con backend/app/models.py. Después de importar este archivo,
-- ejecute desde la raíz del proyecto:
--
-- backend\.venv\Scripts\flask.exe --app backend/run.py init-db
-- backend\.venv\Scripts\flask.exe --app backend/run.py seed-demo

SELECT 'Base itam_sbn creada correctamente' AS resultado;
