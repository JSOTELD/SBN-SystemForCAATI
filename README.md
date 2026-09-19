# Gestor de activos TI físicos

Plataforma para registrar, operar y controlar el ciclo de vida de activos tecnológicos
físicos: identificación, ubicación, responsable, estado, agrupación, inventario,
movimientos, evidencias y trazabilidad operativa.

El diseño toma como referencia prácticas de gestión de servicios de ITIL y los controles
de gestión de servicios de ISO/IEC 20000. Esta referencia orienta los procesos del sistema;
no constituye una certificación ni una declaración de conformidad normativa.

Sistema local actualizado el 13/09/2026. Acceso: **http://localhost:3001**.
Para iniciar nuevamente, active MySQL/MariaDB de XAMPP y ejecute `INICIAR_SISTEMA.cmd`.
El servidor escucha en 127.0.0.1; ese enlace corresponde a esta computadora.

## Perfiles y cuentas iniciales

| Perfil | Usuario local | Alcance |
| --- | --- | --- |
| Administrador | admin | Catálogo, ciclo de vida, agrupaciones, jornadas, cuentas operativas y auditoría |
| Usuario operativo | usuario | Verificación física, evidencias y actualización de activos en sedes asignadas |
| Analista | investigador | Mediciones, indicadores, cobertura operativa y auditoría de guías |

Las contraseñas se entregan en la conversación; se almacenan mediante hashes scrypt.
Estas cuentas genéricas son únicamente para la preparación inicial. Las cuentas personales
creadas desde Usuarios deben cambiar su contraseña temporal al ingresar.

El administrador controla la operación de activos y no modifica las mediciones del analista.
El analista no administra usuarios operativos ni modifica directamente las fichas de activos.
El usuario operativo verifica activos, registra evidencias y reporta hallazgos en sus sedes.

Las cuentas de investigación se crean mediante el procedimiento técnico independiente:

```powershell
backend/.venv-local/Scripts/python.exe -m flask --app backend/run.py create-researcher
backend/.venv-local/Scripts/python.exe -m flask --app backend/run.py reset-researcher-password investigador
```

La separación se aplica en cada petición del servidor, además del menú por perfil.
Quien controla directamente el servidor o la base de datos conserva acceso técnico;
la separación de perfiles no constituye aislamiento frente a ese operador.

## Inventario y marco censal conservados

Inventario general: **5958 activos**, procedentes del Excel entregado.
Estudio vigente: **censo de 1693 equipos de cómputo**, sin impresoras ni periféricos:

| Edificio | Tipo 1 | Tipo 2 | Total |
| --- | ---: | ---: | ---: |
| Libros | 1319 | 247 | 1566 |
| El Comercio | 96 | 31 | 127 |
| Total | 1415 | 278 | 1693 |

Población y cobertura objetivo son iguales: **N = n = 1693**. No hay sorteo ni
margen de error muestral. Se incluyen equipos no operativos y sin dato.
Los códigos C-0001 a C-1566 de Libros se conservaron; El Comercio utiliza
C-1567 a C-1693. Otras sedes permanecen en el inventario general.

La muestra original de 361 equipos permanece archivada como antecedente.
No se generaron mediciones pretest/postest ni hallazgos durante la actualización.

## Flujo de trabajo

1. El administrador crea una jornada, selecciona la sede y asigna usuarios operativos.
2. El usuario abre Mis jornadas, consulta la etiqueta con cámara, teclado o lector externo,
   revisa la ficha del activo y registra coincidencia, diferencia, no localizado o no aplica.
3. Puede adjuntar hasta tres fotografías JPEG/PNG de 5 MB por hallazgo. Se reexportan
   sin EXIF/GPS y se almacenan fuera de los archivos públicos. Solo usuarios autorizados
   pueden consultarlas. El investigador consulta los hallazgos textuales del censo.
4. Las correcciones de hallazgos exigen motivo y versión actual. El administrador
   revisa los hallazgos y puede corregir la ficha con motivo e historial antes/después.
   Los hallazgos no sobrescriben automáticamente la información operativa ni las mediciones.
5. El administrador cierra jornadas. El investigador registra sus propias guías,
   consulta cobertura por sede/tipo/fase y exporta pares e instrumentos.

Se prepararon dos jornadas iniciales asignadas a `usuario`: Libros y El Comercio.
No se cerraron ni se rellenaron con hallazgos.

## Investigación y trazabilidad

Al guardar la primera medición se conserva una copia del marco censal. Cambiar una ficha
operativa posteriormente no altera esa ubicación o descripción histórica del estudio.
Las correcciones de mediciones exigen motivo y comprobación de la versión consultada.
Las fases cerradas no admiten cambios; cerrar con pendientes requiere confirmación y motivo.
La reapertura no está habilitada: deberá definirse un procedimiento de corrección excepcional.

Las exportaciones pareadas omiten SBN y utilizan códigos C-####. Los registros sin
pareja no se incluyen en los resultados pareados. Los indicadores sin observaciones
se muestran como «Sin mediciones». Hay diccionario de variables y auditoría del estudio.
El registro operativo distingue «no localizado» y «no aplica»; no se convierten en tiempo cero.

## Celular y sesiones

Interfaz con menú móvil, formularios táctiles y paginación. Lectura real mediante ZXing
0.1.5 alojado localmente, sin enviar imágenes a un servicio externo. Requiere HTTPS y
permiso de cámara (localhost permite pruebas locales). El ingreso manual sigue disponible.

La sesión utiliza cookies HttpOnly, protección CSRF y Secure en producción. Cambiar
contraseña, desactivar cuenta o cerrar sesión revoca sesiones anteriores. El control
de intentos de acceso queda persistido en la base de datos.

El formulario de hallazgos conserva un borrador en sessionStorage de la pestaña si se
pierde conexión; no guarda la fotografía. El usuario debe volver a enviar el borrador
cuando haya conexión. No es una aplicación completamente offline: aún no hay cola de
sincronización, caché de inventario ni recuperación tras cerrar la pestaña.

## Procedencia y mantenimiento

Fuente: `Base_patrimonial_consolidada_poblacion_muestra_TI.xlsx`, que declara datos al
08/05/2026. No se ha certificado vigencia física de estos registros.
Se conservaron 1410 códigos alfanuméricos de origen, señalados para revisión institucional;
no se sustituyeron letras ni se generaron SBN. Las 160 exclusiones permanecen archivadas.
Las seis hojas y todas sus columnas están en `patrimonial_imports` y `patrimonial_source_chunks`.
El archivo original no se modificó.

```powershell
backend/.venv-local/Scripts/python.exe -m flask --app backend/run.py upgrade-production-db
backend/.venv-local/Scripts/python.exe -m flask --app backend/run.py import-patrimonial "C:/ruta/archivo.xlsx" --dry-run
backend/.venv-local/Scripts/python.exe backend/verify_import.py "C:/ruta/archivo.xlsx"
backend/.venv-local/Scripts/python.exe backend/test_profiles.py
backend/.venv-local/Scripts/python.exe backend/test_compatibility.py
```

La migración añade perfiles, versiones y tablas sin reconstruir el inventario o censo.
Las cuentas antiguas ASSET_MANAGER pasan a usuario general y requieren asignaciones.
El importador impide duplicar el mismo archivo y rechaza sobrescribir registros de otro libro
sin conciliación. El verificador comprueba la entrega de 5958 activos y censo vigente de 1693.

Respaldos: `database/backup_before_roles_mobile.sql` (antes de esta actualización) y
`database/backup_ready_for_host.sql` (estado preparado). Configuración privada: `backend/.env`.
Las fotos están en `backend/private_uploads` o en UPLOAD_FOLDER. Respaldar ambos: base y fotos.

## Despliegue y verificación

Preparación en [deployment/README.md](deployment/README.md): Docker, MariaDB privada,
proxy HTTPS y respaldo. **No se ha publicado**: faltan proveedor, dominio y servidor.
El arranque de producción rechaza las cuentas genéricas y la contraseña local del administrador.

Pruebas realizadas: permisos por rol y ámbito, sesiones/CSRF/revocación, conflictos de
edición, fotografías privadas, congelamiento de marco, cierre de fases, compatibilidad
de agrupaciones, integridad de los datos y restauración de SQL en una base temporal.
Las pantallas y guías se probaron con DOM automatizado contra la API local, sin modificar
datos reales. No había navegador conectado; quedan pendientes pruebas visuales y de
cámara en Android/iPhone. Docker no está instalado aquí: el despliegue preparado debe
validarse en el servidor elegido antes de publicar.

## Referencias de implementación

Las acotaciones están incluidas en los servicios y controles que utilizan cada fuente.

- Libro entregado: definición, resumen, consolidado, muestra, exclusiones y vínculo de guías.
- OWASP: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- SQLAlchemy: https://docs.sqlalchemy.org/en/20/orm/session_transaction.html
- Flask-JWT-Extended: https://flask-jwt-extended.readthedocs.io/en/stable/token_locations.html
- Cámara: https://github.com/zxing-js/browser
- Pillow: https://pillow.readthedocs.io/en/stable/reference/Image.html
- Flask: https://flask.palletsprojects.com/en/stable/deploying/

Referencias consultadas el 13/09/2026. No implican certificación normativa o metodológica externa.
# Guías y auditoría

La interfaz incluye inicio por perfil, menú agrupado según permisos, accesos móviles a inicio/búsqueda/lector, tablas de activos adaptadas a fichas en pantallas pequeñas y filtros con limpieza. Los formularios de hallazgo, medición y activo incluyen identificación, información y revisión antes de guardar; los errores aparecen junto al campo. Se avisa al salir con cambios pendientes. Los indicadores incluyen comparación visual accesible y desglose de cálculo. Las confirmaciones se presentan dentro de la aplicación. Estas mejoras no cambian datos ni permisos; la cámara y la apariencia final deben comprobarse también en un celular real.

En el perfil **Investigador**, abra **Guías y auditoría**. Incluye seis guías de 30 días, 360 registros de fase y 1.693 pares individuales. Los indicadores se calculan desde los totales, sin promediar porcentajes diarios.

El **pretest agregado es real según declaración del usuario**. La fuente identifica ambas fases como no verificadas; esta discrepancia queda visible y pendiente de contrastar con evidencia primaria. Como la fuente contiene agregados diarios, el detalle individual acompaña al informe y no sustituye evidencia primaria. El módulo no modifica las observaciones reales ni los hallazgos operativos.

El botón **Ejecutar conciliación** verifica 360 controles, códigos únicos y hashes SHA-256. El expediente ZIP contiene el archivo original sin cambios, guías CSV, detalle por equipo, conciliaciones, informe imprimible y manifiesto con hashes. Se registran importación, verificaciones y exportaciones en el historial. Los controles no certifican autenticidad de mediciones. Los perfiles administrador y usuario general no acceden al módulo.

Importación reproducible e idempotente: `python -m flask --app backend/run.py import-guides "C:/ruta/guias_30_dias.xlsx" --researcher investigador`. Ejecutar antes `upgrade-production-db` con la misma aplicación. La semilla, versión del algoritmo, fecha de importación y procedencia se conservan en la base de datos. Respaldo previo: `database/backup_before_guides.sql`.

Prueba aislada: `backend/.venv-local/Scripts/python.exe -m unittest discover -s backend -p test_guide_audit.py -v`. Requiere el archivo fuente en la ruta indicada; usa SQLite de pruebas y no altera la base patrimonial.
