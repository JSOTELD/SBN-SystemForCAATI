# Arquitectura funcional

`frontend/index.html` carga app, portal, simulation, usability y dashboards.
JavaScript → HTTP `/api` → Flask `create_app` → registro de blueprints.

- `routes/auth.py` → seguridad/JWT → `User`.
- `routes/assets.py` → validación, seguridad, auditoría → `Asset`, grupos y movimientos.
  Parte de la lógica está directamente en handlers; no existe repository separado.
- `routes/inventory.py` → seguridad, censo/auditoría → jornadas, asignaciones y hallazgos.
- `routes/research.py`, `study.py` → servicios research/census → muestra, fases,
  observaciones e indicadores del estudio.
- `routes/simulation.py` → servicio simulation → modelos de simulación.
- `routes/admin.py` → seguridad/auditoría → cuentas y administración operativa.
- Servicios → modelos de `models.py` → `extensions.db` → SQLAlchemy → MySQL/MariaDB.
  Las pruebas usan SQLite aislado. `services/schema.py` contiene ayudas de esquema;
  Flask-Migrate configurado, sin historial de migraciones en este árbol.

Seguridad y validación son transversales. Frontend comparte funciones globales;
sus referencias y llamadas API se detectan heurísticamente. La resolución exacta
de llamadas dinámicas requiere inspección puntual. Las aristas indican dependencia
estática potencial, no ejecución garantizada ni todos los efectos transitivos.
