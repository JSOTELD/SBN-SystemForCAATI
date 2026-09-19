import time
import hashlib
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token, set_access_cookies, unset_jwt_cookies
from werkzeug.security import check_password_hash, generate_password_hash
# Bibliografía: Werkzeug, Security Helpers (consulta 2026-09-13).
# https://werkzeug.palletsprojects.com/en/stable/utils/#werkzeug.security.generate_password_hash

from ..extensions import db
from ..models import User, LoginThrottle
from ..security import auth_required, current_user
from ..services.audit import audit
from ..services.research import is_strong_password
from ..validation import ValidationFailure, data, required

auth_bp = Blueprint("auth", __name__)
WINDOW = 15 * 60


@auth_bp.get("/health")
def health():
    started = time.perf_counter()
    from sqlalchemy import text
    from sqlalchemy.exc import SQLAlchemyError
    try:
        db.session.execute(text('SELECT 1'))
    except SQLAlchemyError:
        db.session.rollback()
        return {'status': 'unavailable', 'service': 'itam-sbn-api', 'database': 'unavailable'}, 503
    return {"status": "ok", "service": "itam-sbn-api", "database": "mysql",
            "database_latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "timestamp": datetime.now(timezone.utc).isoformat()}


@auth_bp.post("/auth/login")
def login():
    payload = data(); username = required(payload.get("username"), "username"); password = required(payload.get("password"), "password")
    key = hashlib.sha256(f'{request.remote_addr}:{username.lower()}'.encode()).hexdigest()
    now = int(time.time())
    # Persistencia compartida entre procesos y reinicios del servicio.
    attempt = db.session.get(LoginThrottle, key)
    if attempt is None:
        attempt = LoginThrottle(key=key, failures=0, started=now, blocked_until=0)
        db.session.add(attempt)
    if attempt.blocked_until > now:
        retry = attempt.blocked_until - now + 1
        response = jsonify(message=f"Demasiados intentos fallidos. Intente nuevamente en {(retry + 59) // 60} minuto(s).")
        response.status_code = 429; response.headers["Retry-After"] = str(retry); return response
    if attempt.started + WINDOW <= now:
        attempt.failures = 0; attempt.started = now; attempt.blocked_until = 0
    user = db.session.execute(db.select(User).where((User.username == username) | (User.email == username))).scalar_one_or_none()
    if not user or not user.active or not check_password_hash(user.password_hash, password):
        attempt.failures += 1
        if attempt.failures >= 5: attempt.blocked_until = now + WINDOW
        audit(None, "LOGIN_FAILED", "AUTH", details={'accountHash': hashlib.sha256(username.lower().encode()).hexdigest()}); db.session.commit()
        return jsonify(message="Usuario o contraseña incorrectos."), 401
    db.session.delete(attempt); audit(user.id, "LOGIN", "AUTH", user.id); db.session.commit()
    token = create_access_token(identity=user.id, additional_claims={'sv': user.session_version})
    response = jsonify(user=user.public())
    set_access_cookies(response, token)
    return response


@auth_bp.post('/auth/logout')
@auth_required
def logout():
    user = current_user(); user.session_version += 1
    db.session.commit()
    response = jsonify(message='Sesiones cerradas.')
    unset_jwt_cookies(response)
    return response


@auth_bp.get("/auth/me")
@auth_required
def me(): return current_user().public()


@auth_bp.post("/auth/change-password")
@auth_required
def change_password():
    payload = data(); old = required(payload.get("currentPassword"), "currentPassword"); new = required(payload.get("newPassword"), "newPassword")
    user = current_user()
    if not check_password_hash(user.password_hash, old): return jsonify(message="La contraseña actual es incorrecta."), 400
    if not is_strong_password(new): raise ValidationFailure("La contraseña debe tener al menos 12 caracteres e incluir mayúscula, minúscula, número y símbolo.")
    if check_password_hash(user.password_hash, new): return jsonify(message="La nueva contraseña debe ser diferente de la actual."), 400
    user.password_hash = generate_password_hash(new, method="scrypt"); user.must_change_password = False; user.password_changed_at = datetime.now(timezone.utc)
    user.session_version += 1
    audit(user.id, "CHANGE_PASSWORD", "USER", user.id); db.session.commit()
    response = jsonify(message='Contraseña actualizada. Inicie sesión nuevamente.')
    unset_jwt_cookies(response)
    return response
