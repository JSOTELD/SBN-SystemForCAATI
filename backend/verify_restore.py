"""Verifica un dump local de XAMPP en una base temporal, nunca en itam_sbn."""
import re
import subprocess
import sys
import uuid
from pathlib import Path

mysql = Path('C:/xampp/mysql/bin/mysql.exe')
dump = Path(sys.argv[1]).resolve()
name = 'itam_restore_check_' + uuid.uuid4().hex[:12]
assert re.fullmatch(r'itam_restore_check_[a-f0-9]{12}', name)
def sql(statement):
    return subprocess.run([str(mysql), '-u', 'root', '-N', '-e', statement], check=True, capture_output=True, text=True).stdout

# El dump debe estar generado sin --databases ni --all-databases.
content = dump.read_text(encoding='utf-8')
if re.search(r'^\s*(?:USE |CREATE DATABASE|DROP DATABASE)', content, re.M | re.I):
    raise SystemExit('El dump cambia de base; no se restaura automáticamente.')
sql(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4')
try:
    with dump.open('rb') as source:
        subprocess.run([str(mysql), '-u', 'root', name], stdin=source, check=True, capture_output=True)
    counts = sql(f'SELECT (SELECT COUNT(*) FROM `{name}`.assets), (SELECT COUNT(*) FROM `{name}`.research_sample), (SELECT COUNT(*) FROM `{name}`.users)')
    assert counts.strip().split('\t') == ['5958', '1693', '3'], counts
    print('PASS restauración aislada: 5958 activos, 1693 equipos del censo y 3 usuarios.')
finally:
    # Solo la base temporal creada por esta ejecución y validada arriba.
    sql(f'DROP DATABASE `{name}`')
