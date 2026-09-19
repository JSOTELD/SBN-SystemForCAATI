import click
from flask import current_app
from werkzeug.security import generate_password_hash

from .extensions import db
from .models import Asset, AssetGroup, AssetGroupMember, Catalog, ResearchSettings, User


CATALOGS = [
    ("ASSET_TYPE", "TYPE_1", "Tipo 1 - All in One"), ("ASSET_TYPE", "TYPE_2", "Tipo 2 - Sobremesa"),
    ("ASSET_TYPE", "TYPE_3", "Tipo 3 - Sobremesa"), ("ASSET_TYPE", "LAPTOP", "Laptop"),
    ("ASSET_TYPE", "PRINTER", "Impresora"), ("STATUS", "OPERATIVO", "Operativo"),
    ("ASSET_TYPE", "ALL_IN_ONE", "Equipo All in One"), ("ASSET_TYPE", "MONITOR", "Monitor"),
    ("ASSET_TYPE", "KEYBOARD", "Teclado"), ("ASSET_TYPE", "CPU", "CPU"),
    ("STATUS", "MANTENIMIENTO", "En mantenimiento"), ("STATUS", "BAJA", "De baja"),
    ("CONDITION", "BUENO", "Bueno"), ("CONDITION", "REGULAR", "Regular"), ("CONDITION", "MALO", "Malo"),
    ("CONDITION", "NUEVO", "Nuevo"), ("CONDITION", "FALTANTE", "Faltante"),
    ("STATUS", "NO_OPERATIVO", "No operativo"), ("STATUS", "INOPERATIVO", "Inoperativo"),
    ("STATUS", "SIN_DATO", "Sin dato")]


def seed_database(include_reference=False):
    if not db.session.scalar(db.select(User.id).limit(1)):
        db.session.add(User(username="admin", email="admin@entidad.gob.pe", full_name="Administrador local", role="ADMIN",
                            password_hash=generate_password_hash("Admin123!Temporal", method="scrypt"), must_change_password=True))
    for category, code, label in CATALOGS:
        if not db.session.execute(db.select(Catalog).where(Catalog.category == category, Catalog.code == code)).scalar_one_or_none():
            db.session.add(Catalog(category=category, code=code, label=label))
    if not db.session.get(ResearchSettings, 1): db.session.add(ResearchSettings(id=1))
    reference_assets = [
        {"sbn": "999999000001", "internal_code": "REF-001", "asset_type": "TYPE_1",
         "description": "Equipo All in One", "brand": "Lenovo", "model": "ThinkCentre M90a",
         "serial_number": "SN-REF-001", "executing_unit": "UE-024", "site": "Sede Central LIBROS",
         "status": "OPERATIVO", "condition": "BUENO", "responsible_person": "Usuario del área",
         "processor": "Intel Core i5", "memory": "16 GB", "storage": "512 GB SSD", "operating_system": "Windows 11"},
        {"sbn": "999999000002", "internal_code": "REF-002", "asset_type": "TYPE_2",
         "description": "Unidad central de procesamiento", "brand": "Dell", "model": "OptiPlex 7090",
         "serial_number": "SN-REF-002", "executing_unit": "UE-026", "site": "Sede Central LIBROS",
         "status": "OPERATIVO", "condition": "BUENO", "responsible_person": "Usuario del área",
         "processor": "Intel Core i7", "memory": "16 GB", "storage": "1 TB SSD", "operating_system": "Windows 11"},
        {"sbn": "999999000003", "internal_code": "REF-003", "asset_type": "PRINTER",
         "description": "Impresora", "brand": "HP", "model": "LaserJet Pro",
         "serial_number": "SN-REF-003", "executing_unit": "UE-116", "site": "Sede Anexa",
         "status": "OPERATIVO", "condition": "REGULAR", "responsible_person": "Usuario del área"},
    ]
    if include_reference:
        for values in reference_assets:
            if not db.session.execute(db.select(Asset).where(Asset.sbn == values["sbn"])).scalar_one_or_none():
                db.session.add(Asset(**values, installed_software=[], record_complete=True,
                                     record_consistent=True, correctly_registered=True,
                                     record_updated=True, barcode_verified=True))
        component_assets = [
            ("888100000001", "AIO-01", "ALL_IN_ONE", "All in One con procesador integrado", "Lenovo", "ThinkCentre M90a", "AIO-LNV-001"),
            ("888100000002", "TEC-01", "KEYBOARD", "Teclado del equipo All in One", "Lenovo", "Essential USB", "KB-LNV-001"),
            ("888200000001", "MON-21", "MONITOR", "Monitor LED 24 pulgadas", "Dell", "P2422H", "MON-DELL-021"),
            ("888200000002", "TEC-21", "KEYBOARD", "Teclado USB institucional", "Dell", "KB216", "KB-DELL-021"),
            ("888200000003", "CPU-21", "CPU", "CPU de escritorio Tipo 2", "Dell", "OptiPlex 7090", "CPU-DELL-021"),
            ("888300000001", "MON-31", "MONITOR", "Monitor profesional 27 pulgadas", "HP", "Z27", "MON-HP-031"),
            ("888300000002", "TEC-31", "KEYBOARD", "Teclado para Workstation", "HP", "Business Slim", "KB-HP-031"),
            ("888300000003", "CPU-31", "CPU", "CPU Workstation de alto rendimiento", "HP", "Z4 G5", "CPU-HP-031"),
            ("888900000001", "MON-SG", "MONITOR", "Monitor pendiente de agrupación", "Samsung", "S24R350", "MON-SG-001"),
            ("888900000002", "TEC-SG", "KEYBOARD", "Teclado pendiente de agrupación", "Logitech", "K120", "KB-LGT-001"),
            ("888900000003", "CPU-SG", "CPU", "CPU pendiente de agrupación", "Lenovo", "ThinkCentre M70s", "CPU-LNV-099"),
        ]
        for code, internal, kind, description, brand, model, serial in component_assets:
            if not db.session.execute(db.select(Asset).where(Asset.sbn == code)).scalar_one_or_none():
                db.session.add(Asset(sbn=code, internal_code=internal, asset_type=kind, description=description,
                                     brand=brand, model=model, serial_number=serial, executing_unit="UE-024",
                                     site="Sede Central", building="Edificio A", floor="2", room="Oficina 204",
                                     organizational_unit="Tecnologías de la Información", status="OPERATIVO", condition="BUENO",
                                     responsible_person="Usuario de prueba", installed_software=[], record_complete=True,
                                     record_consistent=True, correctly_registered=True, record_updated=True, barcode_verified=True))
        db.session.flush()
        groups = [
            ("GR-AIO-001", "ALL_IN_ONE", "Puesto All in One 01", [("888100000001", "INTEGRATED_UNIT"), ("888100000002", "KEYBOARD")]),
            ("GR-T2-001", "TYPE_2", "Puesto PC Tipo 2 - 01", [("888200000001", "MONITOR"), ("888200000002", "KEYBOARD"), ("888200000003", "CPU")]),
            ("GR-T3-001", "TYPE_3", "Workstation 01", [("888300000001", "MONITOR"), ("888300000002", "KEYBOARD"), ("888300000003", "CPU")]),
        ]
        for code, kind, name, members in groups:
            group = db.session.execute(db.select(AssetGroup).where(AssetGroup.code == code)).scalar_one_or_none()
            if not group:
                group = AssetGroup(code=code, group_type=kind, name=name, site="Sede Central", responsible_person="Usuario de prueba")
                db.session.add(group); db.session.flush()
            for asset_sbn, role in members:
                asset = db.session.execute(db.select(Asset).where(Asset.sbn == asset_sbn)).scalar_one()
                if not asset.group_membership:
                    db.session.add(AssetGroupMember(group=group, asset=asset, component_role=role))
    db.session.commit()


def init_commands(app):
    @app.cli.command('import-guides')
    @click.argument('path',type=click.Path(exists=True,dir_okay=False))
    @click.option('--researcher',default='investigador')
    def import_guides(path,researcher):
        from .services.guide_audit import import_guides
        user=db.session.scalar(db.select(User).where(User.username==researcher,User.role=='RESEARCHER'))
        if not user: raise click.ClickException('Se requiere un investigador existente.')
        study,created=import_guides(path,user.id)
        click.echo(f'Guías {study.id}: {"creadas" if created else "ya importadas"}; {study.manifest["population"]} pares individuales derivados; {study.manifest["checks"]} controles.')

    @app.cli.command('trim-guide-days')
    @click.option('--through-day', type=click.IntRange(1, 30), required=True)
    @click.option('--month', type=click.IntRange(1, 12), default=None)
    @click.option('--year', type=click.IntRange(2000, 2100), default=None)
    @click.option('--apply', is_flag=True, help='Aplica el recorte. Sin esta opción solo informa.')
    def trim_guide_days(through_day, month, year, apply):
        """Conserva guías y detalles hasta un día calendario del estudio."""
        from .models import GuideStudy, GuideAsset
        from .services.guide_audit import METRICS, digest
        studies = db.session.scalars(db.select(GuideStudy)).all()
        if not studies:
            raise click.ClickException('No hay estudios de guías para recortar.')
        total_removed = 0
        for study in studies:
            kept_by_metric = {}
            for metric in METRICS:
                guide = study.guides.get(metric)
                if not guide:
                    raise click.ClickException(f'{study.id}: falta la guía {metric}.')
                kept = []
                for row in guide['rows']:
                    dates = [row[phase]['date'] for phase in ('PRETEST', 'POSTTEST')]
                    if (month is not None and year is not None and
                            any(int(value[0:4]) != year or int(value[5:7]) != month for value in dates)):
                        raise click.ClickException(f'{study.id}: una fecha no corresponde a {year:04d}-{month:02d}.')
                    if row['day'] <= through_day:
                        kept.append(row)
                kept_by_metric[metric] = kept
            details = db.session.scalars(db.select(GuideAsset).where(GuideAsset.study_id == study.id)).all()
            remove = [asset for asset in details if asset.pre.get('day', 0) > through_day or asset.post.get('day', 0) > through_day]
            click.echo(f'{study.filename}: conservar {len(kept_by_metric["PRCC"])} días; eliminar {len(remove)} detalles.')
            if not apply:
                continue
            guides_payload = dict(study.guides)
            for metric in METRICS:
                guide = dict(study.guides[metric])
                guide['rows'] = kept_by_metric[metric]
                summaries = {}
                for phase in ('PRETEST', 'POSTTEST'):
                    denominator = sum(row[phase]['denominator'] for row in guide['rows'])
                    numerator = sum(row[phase]['numerator'] for row in guide['rows'])
                    multiplier = 100 if guide['unit'] == '%' else 1
                    summaries[phase] = {'denominator': denominator, 'numerator': numerator,
                                        'value': numerator / denominator * multiplier}
                guide['summary'] = summaries
                guides_payload[metric] = guide
            study.guides = guides_payload
            for asset in remove:
                db.session.delete(asset)
            kept_details = [{'sample_code': asset.sample_code, 'snapshot': asset.snapshot,
                             'pre': asset.pre, 'post': asset.post}
                            for asset in sorted(details, key=lambda item: item.sample_code)
                            if asset not in remove]
            study.manifest = {**study.manifest, 'population': len(kept_details),
                              'checks': len(METRICS) * 2 * through_day,
                              'passedChecks': len(METRICS) * 2 * through_day,
                              'retainedThroughDay': through_day,
                              'removedFromDay': through_day + 1, 'calendarMonth': month,
                              'calendarYear': year, 'detailsHash': digest(kept_details),
                              'guidesHash': digest(study.guides),
                              'statement': 'Guías recortadas al periodo observado; no se conservaron simulaciones posteriores.'}
            total_removed += len(remove)
        if apply:
            db.session.commit()
            click.echo(f'Recorte aplicado. Detalles eliminados: {total_removed}.')
        else:
            db.session.rollback()
            click.echo('Simulación completada. Usa --apply para confirmar el recorte.')

    @app.cli.command('seed-synthetic-observations')
    @click.option('--apply', is_flag=True, help='Inserta las observaciones sintéticas.')
    def seed_synthetic_observations(apply):
        """Genera observaciones coherentes y explícitamente sintéticas desde las guías."""
        from datetime import datetime, timezone
        from .models import GuideStudy, GuideAsset, Observation, ReportTrial, AuditLog
        study = db.session.scalar(db.select(GuideStudy).order_by(GuideStudy.created_at.desc()))
        if not study:
            raise click.ClickException('No existe un estudio de guías.')
        researcher = db.session.scalar(db.select(User).where(User.role == 'RESEARCHER', User.active.is_(True)))
        if not researcher:
            raise click.ClickException('Se requiere una cuenta RESEARCHER activa.')
        assets = db.session.scalars(db.select(GuideAsset).where(GuideAsset.study_id == study.id)).all()
        existing = db.session.scalar(db.select(db.func.count()).select_from(Observation).where(Observation.notes.like('[SYNTHETIC]%')))
        if existing:
            click.echo(f'Ya existen {existing} observaciones sintéticas. No se duplicaron.')
            return
        click.echo(f'Se prepararían {len(assets) * 2} observaciones sintéticas y {len(assets) * 2} pruebas.')
        if not apply:
            click.echo('Simulación completada. Usa --apply para confirmar.')
            return
        for item in assets:
            for phase, key in (('PRETEST', 'pre'), ('POSTTEST', 'post')):
                row = item.__getattribute__(key)
                observed_at = datetime.fromisoformat(row['date']).replace(hour=12, tzinfo=timezone.utc)
                db.session.add(Observation(
                    phase=phase, asset_id=item.snapshot['asset_id'], record_complete=bool(row['PACI']),
                    record_consistent=bool(row['PACI']), correctly_identified=bool(row['PACI']),
                    identification_method='SYNTHETIC_GUIDE_DERIVATION', identification_duration_ms=int(row['durationMs']),
                    correctly_registered=bool(row['PACI']), record_updated=bool(row['PRA']),
                    notes='[SYNTHETIC] Derivada de guía agregada; reemplazar con observación ministerial.',
                    observed_by=researcher.id, observed_at=observed_at))
                db.session.add(ReportTrial(measurement_code=f'SYN-{item.sample_code}', phase=phase,
                                            report_type='SYNTHETIC_GUIDE_DERIVATION', duration_ms=int(row['durationMs']),
                                            measured_by=researcher.id, measured_at=observed_at))
        db.session.add(AuditLog(user_id=researcher.id, action='SEED_SYNTHETIC', entity_type='OBSERVATION',
                                entity_id=study.id, details={'study': study.filename, 'population': len(assets),
                                'warning': 'Synthetic data; replace before official use.'}))
        db.session.commit()
        click.echo('Datos sintéticos insertados y auditados.')

    @app.cli.command('purge-synthetic-data')
    @click.option('--apply', is_flag=True, help='Elimina observaciones y pruebas marcadas SYNTHETIC.')
    def purge_synthetic_data(apply):
        """Elimina solo datos explícitamente marcados como sintéticos."""
        from .models import Observation, ReportTrial
        observations = db.session.scalars(db.select(Observation).where(Observation.notes.like('[SYNTHETIC]%'))).all()
        trials = db.session.scalars(db.select(ReportTrial).where(ReportTrial.report_type == 'SYNTHETIC_GUIDE_DERIVATION')).all()
        click.echo(f'Encontrados: {len(observations)} observaciones y {len(trials)} pruebas sintéticas.')
        if apply:
            for row in observations + trials:
                db.session.delete(row)
            db.session.commit()
            click.echo('Datos sintéticos eliminados.')
        else:
            db.session.rollback()
            click.echo('Simulación completada. Usa --apply para confirmar.')

    @app.cli.command('disable-account')
    @click.argument('username')
    def disable_account(username):
        user = db.session.execute(db.select(User).where(User.username == username)).scalar_one_or_none()
        if not user: raise click.ClickException('Cuenta no encontrada.')
        if user.role == 'ADMIN' and user.active and db.session.query(User).filter_by(role='ADMIN', active=True).count() < 2:
            raise click.ClickException('No se puede desactivar al último administrador.')
        user.active = False; user.session_version += 1; db.session.commit()
        click.echo('Cuenta desactivada y sesiones revocadas.')

    @app.cli.command('reset-researcher-password')
    @click.argument('username')
    @click.password_option(confirmation_prompt=True)
    def reset_researcher_password(username, password):
        from .services.research import is_strong_password
        from .models import AuditLog
        user = db.session.execute(db.select(User).where(User.username == username, User.role == 'RESEARCHER')).scalar_one_or_none()
        if not user: raise click.ClickException('Investigador no encontrado.')
        if not is_strong_password(password): raise click.ClickException('La clave no cumple la política.')
        user.password_hash = generate_password_hash(password, method='scrypt')
        user.must_change_password = True; user.session_version += 1
        db.session.add(AuditLog(action='RECOVER_RESEARCH_ACCOUNT', entity_type='RESEARCH_ACCOUNT', entity_id=user.id))
        db.session.commit(); click.echo('Contraseña temporal actualizada. Recuperación técnica auditada.')

    @app.cli.command('upgrade-production-db')
    def upgrade_production_db():
        from .services.schema import upgrade_schema
        upgrade_schema()
        click.echo('Migración de perfiles y trabajo móvil completada.')

    @app.cli.command('create-researcher')
    @click.option('--username', prompt=True)
    @click.option('--email', prompt=True)
    @click.option('--name', prompt=True)
    @click.password_option(confirmation_prompt=True)
    def create_researcher(username, email, name, password):
        from .services.research import is_strong_password
        from .validation import required
        if not is_strong_password(password): raise click.ClickException('Se requieren 12 caracteres, mayúscula, minúscula, número y símbolo.')
        user = User(username=required(username, 'usuario', 3, 50), email=required(email, 'correo', 3, 150),
                    full_name=required(name, 'nombre', 3, 150), role='RESEARCHER',
                    password_hash=generate_password_hash(password, method='scrypt'), must_change_password=True)
        db.session.add(user); db.session.commit()
        click.echo('Investigador creado. El administrador operativo no puede restablecer esta cuenta.')

    @app.cli.command('configure-central-census')
    def configure_libros_census():
        from .services.census import configure_census
        user = db.session.execute(db.select(User).where(User.username == 'admin', User.role == 'ADMIN')).scalar_one()
        click.echo(f'Censo Libros y El Comercio configurado: {configure_census(user.id)} equipos.')

    @app.cli.command('import-patrimonial')
    @click.argument('path', type=click.Path(exists=True, dir_okay=False))
    @click.option('--dry-run', is_flag=True, help='Validar sin modificar la base.')
    def import_patrimonial(path, dry_run):
        import json
        from .services.patrimonial import import_workbook
        user = db.session.execute(db.select(User).where(User.username == 'admin', User.role == 'ADMIN')).scalar_one()
        click.echo(json.dumps(import_workbook(path, user.id, dry_run), ensure_ascii=False, indent=2))

    @app.cli.command('upgrade-local-db')
    def upgrade_local_db():
        from sqlalchemy import inspect, text
        db.create_all()
        room = next(c for c in inspect(db.engine).get_columns('assets') if c['name'] == 'room')
        if db.engine.dialect.name == 'mysql' and room['type'].length < 250:
            # El Excel contiene ambientes de hasta 136 caracteres; no truncarlos.
            db.session.execute(text('ALTER TABLE assets MODIFY room VARCHAR(250) NULL'))
            db.session.commit()
        seed_database(include_reference=False)
        click.echo('Esquema actualizado sin eliminar registros.')

    @app.cli.command("init-db")
    def init_db():
        db.create_all(); seed_database(include_reference=False); print("Esquema MySQL y datos iniciales creados.")

    @app.cli.command("seed-reference")
    def seed_reference():
        db.create_all(); seed_database(include_reference=True); print("Datos de referencia creados.")
