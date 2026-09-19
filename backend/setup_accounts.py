"""Crea cuentas iniciales explícitamente solicitadas, sin tocar las existentes.
Ejecutar antes de la puesta en producción. No imprime ni almacena contraseñas en archivos.
"""
import os
from werkzeug.security import generate_password_hash
from app import create_app
from app.extensions import db
from app.models import User, InventorySession, InventoryAssignment, AuditLog

app = create_app()
if os.getenv('APP_ENV') == 'production':
    raise SystemExit('Las cuentas iniciales no se crean en producción.')
with app.app_context():
    admin = db.session.scalar(db.select(User).where(User.username == 'admin'))
    for username, role, name, key in [('investigador','RESEARCHER','Investigador','RESEARCH_PASSWORD'),
                                     ('usuario','INVENTORY','Usuario general','INVENTORY_PASSWORD')]:
        row = db.session.scalar(db.select(User).where(User.username == username))
        if not row:
            password = os.environ[key]
            row = User(username=username, email=username+'@local.invalid', full_name=name, role=role,
                       password_hash=generate_password_hash(password, method='scrypt'), must_change_password=False)
            db.session.add(row); db.session.flush()
            db.session.add(AuditLog(user_id=admin.id, action='CREATE_INITIAL_ACCOUNT', entity_type='USER', entity_id=row.id, details={'role':role}))
        if row.role != role: raise RuntimeError('Nombre ocupado por otro perfil; no se modifica.')
    general = db.session.scalar(db.select(User).where(User.username == 'usuario'))
    for site, name in [('LOCAL SEDE CENTRAL - EDIFICIO LIBROS','Levantamiento inicial - Libros'),
                       ('LOCAL SEDE CENTRAL - EDIFICIO EL COMERCIO','Levantamiento inicial - El Comercio')]:
        session = db.session.scalar(db.select(InventorySession).where(InventorySession.name == name))
        if not session:
            session = InventorySession(name=name, site=site, phase='OPERATIVO', created_by=admin.id)
            db.session.add(session); db.session.flush()
            db.session.add(InventoryAssignment(session_id=session.id, user_id=general.id))
    db.session.commit()
    print('Perfiles iniciales y dos jornadas preparados, sin registrar hallazgos ni mediciones.')
