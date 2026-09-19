"""Create a self-contained MySQL asset inventory from the supplied workbook."""
import argparse
import re
import unicodedata
import uuid
from collections import Counter
from pathlib import Path

from openpyxl import load_workbook


def norm(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value or '')) if not unicodedata.combining(c)).upper().strip()


def category(description):
    value = norm(description)
    if value.startswith('COMPUTADORA PERSONAL PORTATIL'):
        return 'LAPTOP'
    if value.startswith('TECLADO'):
        return 'KEYBOARD'
    if value.startswith('IMPRESORA') or value.startswith('EQUIPO MULTIFUNCIONAL COPIADORA IMPRESORA'):
        return 'PRINTER'
    if value.startswith('MONITOR CON PROCESADOR INTEGRADO'):
        return 'ALL_IN_ONE'
    if value.startswith('UNIDAD CENTRAL DE PROCESO - CPU'):
        return 'CPU'
    if value.startswith('MONITOR') and not any(word in value for word in ('PRESION', 'FORMA DE ONDA', 'VECTOROSCOPIO', 'MONITOREO Y CONTROL')):
        return 'MONITOR'
    return None


def sql(value):
    if value is None or value == '':
        return 'NULL'
    return "'" + str(value).replace('\\', '\\\\').replace("'", "''").replace('\r', ' ').replace('\n', ' ') + "'"


def build(source, output):
    workbook = load_workbook(source, read_only=True, data_only=True)
    sheet = workbook.active
    rows = sheet.iter_rows(values_only=True)
    next(rows, None)
    next(rows, None)
    seen = set()
    records = []
    skipped_invalid = 0
    skipped_duplicate = 0
    for row_number, row in enumerate(rows, 3):
        kind = category(row[16])
        sbn = norm(row[13]).replace(' ', '')
        if not kind:
            continue
        if not re.fullmatch(r'[A-Z0-9]{12}', sbn):
            skipped_invalid += 1
            continue
        if sbn in seen:
            skipped_duplicate += 1
            continue
        seen.add(sbn)
        status = norm(row[23]).replace(' ', '_')
        status = status if status in {'OPERATIVO', 'MANTENIMIENTO', 'BAJA', 'NO_OPERATIVO', 'INOPERATIVO', 'SIN_DATO'} else 'SIN_DATO'
        condition = norm(row[25])
        condition = condition if condition in {'BUENO', 'REGULAR', 'MALO', 'NUEVO', 'FALTANTE'} else 'SIN_DATO'
        records.append((str(uuid.uuid5(uuid.NAMESPACE_URL, 'itam-sbn:' + sbn)), sbn,
                        str(row[14] or row[12] or '').strip() or None, kind,
                        str(row[16] or '').strip(), str(row[17] or '').strip() or None,
                        str(row[18] or '').strip() or None, str(row[20] or '').strip() or None,
                        str(row[5] or '').strip() or None, str(row[6] or '').strip(),
                        str(row[8] or '').strip() or None, str(row[9] or '').strip() or None,
                        str(row[7] or '').strip() or None, status, condition,
                        f'Fuente: {Path(source).name}; fila {row_number}. Importación documental; verificación física pendiente.'))
    workbook.close()
    output.parent.mkdir(parents=True, exist_ok=True)
    columns = ('id', 'sbn', 'internal_code', 'asset_type', 'description', 'brand', 'model', 'serial_number',
               'executing_unit', 'site', 'floor', 'room', 'organizational_unit', 'status', 'condition', 'notes')
    with output.open('w', encoding='utf-8', newline='\n') as handle:
        handle.write('-- ITAM SBN: inventario filtrado para MySQL/MariaDB/XAMPP\n')
        handle.write('-- Fuente: ' + Path(source).name + '\n')
        handle.write('-- Tipos: monitores, teclados, impresoras, laptops, all in one, CPU y workstations.\n')
        handle.write('-- Registros validos: ' + str(len(records)) + '\n')
        handle.write('-- Filas omitidas por SBN invalido: ' + str(skipped_invalid) + '; duplicados: ' + str(skipped_duplicate) + '\n\n')
        handle.write('CREATE DATABASE IF NOT EXISTS itam_sbn CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\nUSE itam_sbn;\n\n')
        handle.write('CREATE TABLE IF NOT EXISTS assets (\n'
                     'id CHAR(36) NOT NULL PRIMARY KEY, sbn VARCHAR(12) NOT NULL UNIQUE, internal_code VARCHAR(100),\n'
                     'asset_type VARCHAR(20) NOT NULL, description VARCHAR(250) NOT NULL, brand VARCHAR(100), model VARCHAR(100),\n'
                     'serial_number VARCHAR(150), executing_unit VARCHAR(30), site VARCHAR(150) NOT NULL, floor VARCHAR(50),\n'
                     'room VARCHAR(250), organizational_unit VARCHAR(150), status VARCHAR(20) NOT NULL, condition VARCHAR(20) NOT NULL,\n'
                     'notes TEXT, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, version INT NOT NULL DEFAULT 1\n'
                     ') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;\n\n')
        handle.write('START TRANSACTION;\n')
        handle.write('DELETE FROM assets;\n')
        col_sql = ', '.join('`' + column + '`' for column in columns + ('created_at', 'updated_at', 'version'))
        for start in range(0, len(records), 250):
            batch = records[start:start + 250]
            handle.write('INSERT INTO assets (' + col_sql + ') VALUES\n')
            values = []
            for record in batch:
                values.append('(' + ','.join(sql(v) for v in record) + ", CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)")
            handle.write(',\n'.join(values) + ';\n')
        handle.write('COMMIT;\n')
    return len(records), Counter(record[3] for record in records), skipped_invalid, skipped_duplicate


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    total, counts, invalid, duplicate = build(args.source, args.output)
    print({'records': total, 'by_type': dict(counts), 'invalid_sbn': invalid, 'duplicate_sbn': duplicate, 'output': str(args.output)})
