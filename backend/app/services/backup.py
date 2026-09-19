"""Backups reproducibles de la base patrimonial para continuidad operativa."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def _dump_executable() -> str:
    configured = os.getenv("MYSQLDUMP_PATH")
    candidates = [configured] if configured else []
    candidates.extend([shutil.which("mysqldump"), r"C:\xampp\mysql\bin\mysqldump.exe"])
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    raise RuntimeError("No se encontró mysqldump. Configure MYSQLDUMP_PATH o instale MySQL/XAMPP.")


def create_backup(app) -> dict:
    """Genera un SQL y un manifiesto SHA-256 sin incluir credenciales en el archivo."""
    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    if not uri.startswith("mysql+pymysql://"):
        raise RuntimeError("El respaldo operativo requiere una base MySQL/MariaDB.")
    from urllib.parse import urlsplit
    parsed = urlsplit(uri.replace("mysql+pymysql://", "mysql://", 1))
    host, port = parsed.hostname or "127.0.0.1", str(parsed.port or 3306)
    database = parsed.path.lstrip("/")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = Path(app.config.get("BACKUP_FOLDER", Path(app.instance_path) / "backups"))
    target.mkdir(parents=True, exist_ok=True)
    sql_path = target / f"itam_sbn_{timestamp}.sql"
    command = [_dump_executable(), "--single-transaction", "--routines", "--triggers", "--hex-blob",
               "--host", host, "--port", port, "--user", parsed.username or "root", database]
    env = os.environ.copy()
    if parsed.password:
        env["MYSQL_PWD"] = parsed.password
    with sql_path.open("wb") as output:
        result = subprocess.run(command, stdout=output, stderr=subprocess.PIPE, env=env, timeout=300)
    if result.returncode != 0:
        sql_path.unlink(missing_ok=True)
        raise RuntimeError(result.stderr.decode("utf-8", "replace").strip() or "mysqldump falló.")
    digest = hashlib.sha256(sql_path.read_bytes()).hexdigest()
    manifest = {"file": sql_path.name, "created_at": timestamp, "sha256": digest,
                "size_bytes": sql_path.stat().st_size, "database": database}
    manifest_path = sql_path.with_suffix(".json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {**manifest, "path": str(sql_path), "manifest": str(manifest_path)}


def verify_backup(path: str | Path) -> dict:
    sql_path = Path(path)
    manifest_path = sql_path.with_suffix(".json")
    if not sql_path.exists() or not manifest_path.exists():
        raise RuntimeError("El SQL y su manifiesto deben existir juntos.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = hashlib.sha256(sql_path.read_bytes()).hexdigest()
    return {"valid": actual == manifest.get("sha256"), "expected": manifest.get("sha256"),
            "actual": actual, "file": str(sql_path)}
