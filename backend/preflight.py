"""Controles previos al arranque público. No cambia usuarios ni datos."""
from werkzeug.security import check_password_hash
from app import create_app
from app.extensions import db
from app.models import User

app = create_app('production')
with app.app_context():
    users = db.session.scalars(db.select(User).where(User.active.is_(True))).all()
    if not any(user.role == 'ADMIN' for user in users):
        raise SystemExit('Falta una cuenta administrativa activa. Importe la base y prepare cuentas personales.')
    for user in users:
        if user.username in {'usuario', 'investigador'} or any(check_password_hash(user.password_hash, password) for password in ['Admin123456!', 'Admin123!Temporal']):
            raise SystemExit('No se publica con cuentas genéricas o contraseña local. Desactive las cuentas iniciales y cambie la clave administrativa.')
    print('Controles de arranque de producción satisfactorios.')
