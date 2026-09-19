#!/bin/sh
# Ejecutar desde deployment; no contiene contraseñas ni elimina respaldos.
set -eu
umask 077
mkdir -p backups
stamp=$(date -u +%Y%m%dT%H%M%SZ)
docker compose exec -T db sh -c 'exec mariadb-dump -u root -p"$MARIADB_ROOT_PASSWORD" --single-transaction itam_sbn' > "backups/itam-$stamp.sql"
docker compose exec -T app tar -czf - -C /srv/itam/uploads . > "backups/photos-$stamp.tar.gz"
echo "Respaldo generado: $stamp"
