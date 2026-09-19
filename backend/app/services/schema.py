"""Migración aditiva e idempotente de la entrega 2026-09-13.

No elimina activos ni reconstruye el censo. Ejecutar con respaldo previo.
SQLAlchemy: https://docs.sqlalchemy.org/en/20/core/reflection.html
"""
from sqlalchemy import inspect, text
from ..extensions import db


def upgrade_schema():
    db.create_all()
    inspector = inspect(db.engine)
    additions = {
        'users': {'session_version': 'INTEGER NOT NULL DEFAULT 1'},
        'assets': {'version': 'INTEGER NOT NULL DEFAULT 1'},
        'observations': {'version': 'INTEGER NOT NULL DEFAULT 1'},
        'inventory_checks': {'version': 'INTEGER NOT NULL DEFAULT 1', 'checked_by': 'VARCHAR(36) NULL'},
    }
    for table, fields in additions.items():
        existing = {c['name'] for c in inspector.get_columns(table)}
        for name, sql_type in fields.items():
            if name not in existing:
                db.session.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {sql_type}'))
    db.session.commit()
    if db.engine.dialect.name == 'mysql':
        for constraint in inspect(db.engine).get_check_constraints('users'):
            if 'role' in constraint.get('sqltext', '').lower() and 'RESEARCHER' not in constraint['sqltext']:
                name = constraint['name'].replace('`', '``')
                db.session.execute(text(f'ALTER TABLE users DROP CONSTRAINT `{name}`'))
                db.session.execute(text("ALTER TABLE users ADD CONSTRAINT ck_users_role CHECK (role IN ('ADMIN','INVENTORY','RESEARCHER','ASSET_MANAGER','VIEWER'))"))
                db.session.commit()
    # Compatibilidad con cuentas antiguas: mismo usuario, permisos operativos mínimos.
    db.session.execute(text("UPDATE users SET role='INVENTORY', session_version=session_version+1 WHERE role='ASSET_MANAGER'"))
    db.session.commit()
