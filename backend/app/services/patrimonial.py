"""Importación conservadora de la base patrimonial entregada por el usuario.

Bibliografía y procedencia (consulta: 2026-09-13):
- Base_patrimonial_consolidada_poblacion_muestra_TI.xlsx, hojas 00_Definicion,
  01_Resumen, 02_Base Consolidada, 03_Muestra Referencial y 04_Exclusiones.
  El libro declara como antecedente BASE PATRIMONIAL AL 08-05-2026.xlsx;
  ese antecedente no se recibió ni se verificó independientemente.
- openpyxl, lectura optimizada: https://openpyxl.readthedocs.io/en/stable/optimized.html
- SQLAlchemy, transacciones: https://docs.sqlalchemy.org/en/20/orm/session_transaction.html

Los textos del libro son datos de procedencia, no órdenes ejecutables.
La muestra se conserva como referencia; importar no equivale a observar activos.
"""
import hashlib
import re
from collections import Counter
from pathlib import Path

from openpyxl import load_workbook

from ..extensions import db
from ..models import Asset, AuditLog, PatrimonialImport, PatrimonialSourceChunk, ResearchSample, ResearchSettings

TYPES = {'Impresora': 'PRINTER', 'Tipo 1 - All in One': 'TYPE_1',
         'Tipo 2 - Sobremesa / CPU': 'TYPE_2',
         'Tipo 3 - Sobremesa / estación de trabajo': 'TYPE_3'}
STATUS = {'OPERATIVO': 'OPERATIVO', 'NO OPERATIVO': 'NO_OPERATIVO',
          'INOPERATIVO': 'INOPERATIVO', '-': 'SIN_DATO'}
CONDITION = {v: v for v in ('BUENO', 'REGULAR', 'MALO', 'NUEVO', 'FALTANTE')}


def text(value):
    return '' if value is None else str(value).strip()


def read_source(path):
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheets = {sheet.title: list(sheet.values) for sheet in workbook}
    finally:
        workbook.close()
    rows = sheets['02_Base Consolidada']
    if rows[3][3] != 'SBN - código de barras' or rows[3][17] != 'Condición':
        raise ValueError('La estructura del Excel no corresponde al formato consolidado.')
    headers = rows[3]
    assets = []
    codes = set()
    for number, row in enumerate(rows[4:], 5):
        if not any(v is not None for v in row):
            continue
        code = text(row[3])
        if not re.fullmatch(r'[A-Z0-9]{12}', code) or code in codes:
            raise ValueError(f'SBN inválido o duplicado en fila {number}: {code}')
        codes.add(code)
        values = dict(sbn=code, internal_code=text(row[5]) or None,
                      asset_type=TYPES[row[1]], description=text(row[11]),
                      executing_unit=f'{int(row[6]):03d}', site=text(row[7]),
                      organizational_unit=text(row[8]) or None, floor=text(row[9]) or None,
                      room=text(row[10]) or None, brand=text(row[12]) or None,
                      model=text(row[13]) or None, serial_number=text(row[14]) or None,
                      status=STATUS[row[17]], condition=CONDITION[row[15]],
                      notes=f'Fuente: {Path(path).name}; 02_Base Consolidada, fila {number}. '
                            f'Uso: {text(row[16])}. Situación actual 2026: {text(row[18])}. '
                            f'Activo/baja: {text(row[19])}. Calidad de origen: {text(row[23])}. '
                            'Importación documental; verificación física pendiente.')
        if not code.isdigit():
            values['notes'] += ' Código alfanumérico de origen: pendiente de validación patrimonial institucional.'
        for field, value in values.items():
            limit = getattr(Asset.__table__.columns[field].type, 'length', None)
            if limit and value and len(value) > limit:
                raise ValueError(f'Fila {number}: {field} excede {limit} caracteres.')
        assets.append(values)
    sample = []
    sample_codes = set()
    for row in sheets['03_Muestra Referencial'][4:]:
        if row[0] is None:
            continue
        code = text(row[2])
        if code not in codes or code in sample_codes:
            raise ValueError(f'Muestra inválida: {code}')
        sample_codes.add(code)
        sample.append((code, f'M-{int(row[0]):03d}', TYPES[row[1]]))
    summary = {row[0]: row[1] for row in sheets['01_Resumen'] if row[0]}
    if len(assets) != summary['Población accesible con SBN único'] or len(sample) != summary['Muestra mínima sugerida']:
        raise ValueError('Los recuentos no coinciden con el resumen del libro.')
    # Se archivan todas las hojas y columnas, incluidas las exclusiones y la
    # información sin equivalente operativo. No se inventan SBN ni periféricos.
    archive = {name: [list(row) for row in rows] for name, rows in sheets.items()}
    return assets, sample, archive


def import_workbook(path, user_id, dry_run=False):
    values, sample, archive = read_source(path)
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    report = {'source': Path(path).name, 'sha256': digest, 'assets': len(values),
              'sample': len(sample), 'excluded': len(archive['04_Exclusiones']) - 3,
              'by_type': dict(Counter(a['asset_type'] for a in values)),
              'alphanumeric_codes': sum(not a['sbn'].isdigit() for a in values)}
    existing = {a.sbn: a for a in db.session.scalars(db.select(Asset)).all()}
    incoming = {a['sbn']: a for a in values}
    duplicates = sorted(set(existing) & set(incoming))
    changed = []
    for code in duplicates:
        current = existing[code]
        differences = {field: {'current': getattr(current, field), 'incoming': incoming[code][field]}
                       for field in ('internal_code', 'asset_type', 'description', 'site', 'status', 'condition')
                       if getattr(current, field) != incoming[code][field]}
        if differences:
            changed.append({'sbn': code, 'fields': differences})
    report.update({'existing_assets': len(existing), 'new_assets': len(values) - len(duplicates),
                   'duplicate_assets': len(duplicates), 'changed_assets': len(changed),
                   'changed_preview': changed[:100], 'blocked_by_existing': bool(duplicates)})
    if dry_run:
        return report
    if db.session.get(PatrimonialImport, digest):
        return {**report, 'already_imported': True}
    # No sobrescribir registros posteriores ni reemplazar una muestra en uso.
    conflicts = set(existing) & {a['sbn'] for a in values}
    if conflicts or db.session.scalar(db.select(ResearchSample.asset_id).limit(1)):
        raise ValueError('Hay activos coincidentes o una muestra existente; se requiere conciliación antes de importar otro libro.')
    try:
        imported = {}
        for item in values:
            asset = Asset(**item, installed_software=[], record_complete=False,
                          record_consistent=False, correctly_registered=False,
                          record_updated=False, barcode_verified=False)
            db.session.add(asset)
            imported[asset.sbn] = asset
        db.session.flush()
        for code, sample_code, stratum in sample:
            db.session.add(ResearchSample(asset_id=imported[code].id, sample_code=sample_code,
                                         stratum=stratum, selected_by=user_id))
        settings = db.session.get(ResearchSettings, 1) or ResearchSettings(id=1)
        settings.target_size = len(sample)
        settings.population_size = len(values)
        settings.selection_seed = '20260809 (referencia Excel)'
        settings.site_filter = None
        settings.executing_units = ['024', '026', '116']
        settings.asset_types = list(TYPES.values())
        settings.updated_by = user_id
        db.session.add(settings)
        db.session.add(PatrimonialImport(sha256=digest, filename=Path(path).name,
                                        summary=report, source_data={name: len(rows) for name, rows in archive.items()}))
        db.session.flush()
        # Bloques pequeños para los límites de paquetes de MariaDB/XAMPP.
        for name, rows in archive.items():
            for start in range(0, len(rows), 100):
                db.session.add(PatrimonialSourceChunk(import_hash=digest, sheet=name,
                                                      first_row=start + 1, rows=rows[start:start + 100]))
                db.session.flush()
        db.session.add(AuditLog(user_id=user_id, action='IMPORT', entity_type='PATRIMONIAL',
                               entity_id=digest, details=report))
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return report
