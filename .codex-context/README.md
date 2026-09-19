# Navegación con contexto mínimo

Desde la raíz, Python 3.10+ sin dependencias:

```sh
python tools/code-context/context.py query "registro activo codigo barras"
python tools/code-context/context.py symbol create_asset
python tools/code-context/context.py impact apply_asset_payload --depth 1
python tools/code-context/context.py update
python tools/code-context/context.py rebuild
python tools/code-context/context.py status
python -m unittest discover -s tools/code-context -p "test_*.py"
```

Consultas: seis resultados por defecto; `--limit` permite 1–100. Impacto: profundidad
2, ampliable con `--depth` hasta 10, hasta cuatro veces `limit` aristas. Usa rutas
relativas con `/` o `archivo:símbolo` para evitar ambigüedad. `uses` y `used_by`
permiten explorar ambos sentidos; las rutas afectadas son potenciales.

Cada consulta comprueba metadatos de archivos y actualiza cambios automáticamente.
No lee contenido sin cambios. Hashes evitan reanalizar archivos solo tocados;
altas, bajas y renombres se incorporan. Relaciones se recomponen desde metadatos
en caché, sin releer fuentes. Cambios del extractor fuerzan reconstrucción.
No ejecutar comandos concurrentes de escritura del índice.

Genera `files-index.json`, `symbols-index.json`, `dependency-graph.json` (adyacencia
de archivos y símbolos), `modules.json`, `routes.json`, `database-map.json`,
`context-version.json` y `cache.json` (metadatos internos, sin fuente completa).
Documentos manuales: este README, resumen y arquitectura.

Se versionan herramienta, pruebas, AGENTS y documentos manuales. JSON derivados
se ignoran por ruido y tamaño; se regeneran automáticamente en la primera consulta
de un checkout. Si la caché está dañada, elimina únicamente `cache.json` y reconstruye.

Python se analiza con AST sin importar/ejecutar la aplicación. Rutas Flask y
modelos SQLAlchemy se extraen del código real. JavaScript usa patrones: funciones,
flechas, clases, referencias globales y rutas API literales; las rutas construidas
dinámicamente y relaciones ambiguas pueden faltar. No es análisis de flujo ni
buscador semántico; consultas en español tienen un pequeño vocabulario de dominio.
SQL se localiza sin duplicar su contenido; el mapa de entidades procede del ORM.
No hay repositorios, DTO ni hooks de framework independientes detectados.

Se excluyen dependencias, entornos, cachés, uploads, outputs, secretos `.env`,
backups, lockfiles, binarios, minificados y archivos mayores de 2 MB. Respeta patrones
comunes de `.gitignore` raíz y anidados, incluida negación; no implementa escapes
avanzados de Git. Las exclusiones de seguridad/dependencias no se pueden negar.
Los enlaces simbólicos se omiten. No se consulta ninguna base de datos.
