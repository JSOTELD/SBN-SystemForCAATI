# ITAM SBN

Gestión de activos TI, inventario por jornadas e investigación censal pre/post.

- Backend: Python, Flask 3.1, blueprints; servicios funcionales, SQLAlchemy 2 vía
  Flask-SQLAlchemy. No hay capa repository independiente.
- Frontend: HTML/CSS y JavaScript global, servido por Flask; ZXing externo
  alojado en `frontend/vendor` (excluido del índice). Sin framework ni build.
- Datos: MySQL/MariaDB mediante PyMySQL; pruebas SQLite en memoria.
- Autenticación: Flask-JWT-Extended, cookies/CSRF, roles y ámbito por sede;
  contraseñas con Werkzeug. Configuración privada mediante `.env` (no indexado).
- Carpetas: `backend/app/routes`, `services`, `models.py`, `security.py`;
  `frontend`; `database` (DDL); `deployment` (Docker/Caddy); `tests/frontend`.
- Dependencias: pip con `backend/requirements.txt`; npm/jsdom para prueba DOM.
  No se detectó configuración propia de lint/indexación previa. Flask-Migrate
  está instalado, sin carpeta de migraciones; `services/schema.py` ayuda al esquema.
- Inicio local: `INICIAR_SISTEMA.cmd` (requiere MySQL); servidor puerto 3001.
- Navegación: `python tools/code-context/context.py query "activos"`;
  `impact Asset --depth 1`; `update`; `rebuild` solo excepcionalmente.
- Pruebas backend: `backend/.venv-local/Scripts/python.exe -m unittest discover -s backend -p "test_*.py"`.
- Pruebas índice: `python -m unittest discover -s tools/code-context -p "test_*.py"`.
- Convenciones: rutas `/api`, modelos centralizados, UUID, permisos en servidor;
  no ejecutar importaciones/restauraciones para validar una tarea de código.
