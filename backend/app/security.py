from functools import wraps

from flask import abort, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, verify_jwt_in_request

from .extensions import db
from .models import User, Asset, ResearchSample, InventorySession, InventoryAssignment

# OWASP Authorization Cheat Sheet: permisos en cada petición, mínimo privilegio.
# https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
def allowed_route(user):
    blueprint = request.blueprint
    role = user.role
    read = request.method in {'GET', 'HEAD'}
    if blueprint == 'auth': return True
    if blueprint in {'research', 'study', 'guide_audit'}: return role == 'RESEARCHER'
    if blueprint == 'admin':
        return role == 'ADMIN' or (request.endpoint == 'admin.catalogs' and read)
    if blueprint == 'inventory': return role in {'ADMIN', 'INVENTORY'}
    if blueprint == 'assets':
        if role == 'ADMIN': return True
        return read and request.endpoint in {'assets.list_assets', 'assets.by_sbn', 'assets.get_asset'} and role in {'INVENTORY', 'RESEARCHER', 'VIEWER'}
    return False


def scoped_assets(query):
    user = current_user()
    if user.role == 'RESEARCHER':
        return query.where(Asset.id.in_(db.select(ResearchSample.asset_id)))
    if user.role == 'INVENTORY':
        sites = db.select(InventorySession.site).join(InventoryAssignment, InventoryAssignment.session_id == InventorySession.id).where(InventoryAssignment.user_id == user.id)
        return query.where(Asset.site.in_(sites))
    return query


def ensure_asset_access(asset):
    if not db.session.scalar(scoped_assets(db.select(Asset.id)).where(Asset.id == asset.id)):
        abort(403, description='El activo no pertenece a su ámbito asignado.')


def current_user():
    return db.session.get(User, get_jwt_identity())


def auth_required(fn):
    @wraps(fn)
    def decorated(*args, **kwargs):
        verify_jwt_in_request()
        user = current_user()
        if not user or not user.active:
            return jsonify(message="La cuenta ya no está activa."), 401
        if get_jwt().get('sv') != user.session_version:
            return jsonify(message='La sesión fue revocada. Inicie sesión nuevamente.'), 401
        if not allowed_route(user):
            return jsonify(message='Su perfil no tiene acceso a esta función.'), 403
        allowed = request.path.endswith("/auth/change-password") or request.path.endswith("/auth/me") or request.path.endswith('/auth/logout')
        if user.must_change_password and not allowed:
            return jsonify(message="Debe cambiar la contraseña temporal antes de continuar.", code="PASSWORD_CHANGE_REQUIRED"), 403
        return fn(*args, **kwargs)
    return decorated


def roles_required(*roles):
    def wrapper(fn):
        @wraps(fn)
        @auth_required
        def decorated(*args, **kwargs):
            if current_user().role not in roles:
                return jsonify(message="No cuenta con permisos para realizar esta operación."), 403
            return fn(*args, **kwargs)
        return decorated
    return wrapper
