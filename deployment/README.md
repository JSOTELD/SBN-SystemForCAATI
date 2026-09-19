# Publicación pendiente: guía para el servidor elegido

Se requiere alojamiento que ejecute Python/Flask de forma permanente. Esta opción
usa Linux con Docker Compose, MariaDB y Caddy; un hosting limitado a PHP no ejecuta
esta configuración. Aún no se eligió proveedor ni dominio y no se publicó nada.

## Preparar la copia de publicación

1. Conservar un respaldo verificable de MySQL y de las fotografías.
2. En la aplicación local, crear las cuentas personales operativas y cambiar la
   contraseña básica del administrador por una definitiva.
3. Crear investigadores personales mediante `create-researcher` en la consola técnica.
4. Desactivar las cuentas genéricas en la copia destinada a publicar:

```powershell
backend/.venv-local/Scripts/python.exe -m flask --app backend/run.py disable-account usuario
backend/.venv-local/Scripts/python.exe -m flask --app backend/run.py disable-account investigador
```

5. Generar un dump nuevo sin `--databases` ni `--all-databases`. La copia
   `backup_ready_for_host.sql` conserva las cuentas iniciales; sirve para
   recuperación local, pero no supera los controles de producción por sí sola.
6. Configurar dominio/DNS, elegir el responsable técnico de recuperación de investigadores
   y definir la frecuencia, ubicación externa y retención de los respaldos.

## Arranque en el servidor (desde deployment)

Copiar `.env.example` a `.env` y completar DOMAIN, claves MySQL y un JWT_SECRET aleatorio
de al menos 32 caracteres. No reutilizar secretos iniciales ni incluir `.env` en Git.
Solo el proxy publica 80/443; la base de datos queda en la red interna de Docker.

```sh
docker compose up -d db
docker compose build app
# Importar el SQL previamente transferido al servidor:
docker compose exec -T db sh -c 'exec mariadb -u root -p"$MARIADB_ROOT_PASSWORD" itam_sbn' < copia-publicacion.sql
docker compose up -d
```

El dominio debe resolver al servidor y los puertos 80/443 deben estar disponibles para
que Caddy obtenga HTTPS. El volumen `photos` conserva imágenes; copiar las fotografías
existentes antes del uso real si hubiera evidencias locales.

El arranque aplica la migración aditiva, verifica que exista un administrador y rechaza
cuentas genéricas activas o las contraseñas iniciales conocidas. No garantiza por sí solo
la seguridad integral: validar las políticas del proveedor y las cuentas personales.

## Respaldos y recuperación

Ejecutar `sh backup.sh` desde esta carpeta. Genera SQL y archivo de fotografías con
permisos privados. Programarlo diariamente con el planificador del servidor, por ejemplo:

```text
0 2 * * * cd /ruta/itam/deployment && sh backup.sh >> backup.log 2>&1
```

No deja una retención destructiva predeterminada. Transferir una copia a una ubicación
externa restringida y realizar restauraciones periódicas en un entorno de prueba.
Para recuperar, detener escrituras, restaurar SQL en una base limpia y recuperar fotos
de la misma fecha. Verificar activos, marco censal, cuentas y enlaces de evidencia antes
de volver a habilitar el acceso.

## Prueba piloto antes del uso institucional

- Login/logout y contraseñas definitivas por perfil; administrador sin acceso a tesis.
- Usuario general restringido a jornadas asignadas; investigador con su censo de 1693.
- Cámara, permisos, lectura de códigos numéricos/alfanuméricos y carga de fotos en
  Android y iPhone. Probar denegación del permiso e ingreso manual.
- Red lenta, interrupciones y reenvío de borradores; dos usuarios corrigiendo el mismo hallazgo.
- Restauración de respaldo y persistencia tras reiniciar contenedores.
- Revisión de consumo y tiempos con el número real de usuarios simultáneos.

Esta configuración no se ejecutó aquí porque Docker no está instalado. La validación
local cubre la aplicación y la base XAMPP, no el proveedor que se contrate.
