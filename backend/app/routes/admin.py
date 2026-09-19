import json
import tempfile
from pathlib import Path
from flask import Blueprint, current_app, jsonify, request
from werkzeug.security import generate_password_hash

from ..extensions import db
from ..models import AuditLog, Catalog, User
from ..security import auth_required, current_user, roles_required
from ..services.audit import audit
from ..services.research import is_strong_password
from ..validation import ValidationFailure, data, required

admin_bp=Blueprint("admin",__name__)

@admin_bp.post('/patrimonial/import-preview')
@roles_required('ADMIN')
def patrimonial_import_preview():
    upload = request.files.get('file')
    if not upload or not upload.filename.lower().endswith(('.xlsx', '.xlsm')):
        return jsonify(message='Adjunte un libro Excel .xlsx o .xlsm.'), 400
    from ..services.patrimonial import import_workbook
    suffix = Path(upload.filename).suffix.lower()
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp:
            upload.save(temp.name); path = temp.name
        return import_workbook(path, current_user().id, dry_run=True)
    except (OSError, ValueError) as error:
        return jsonify(message=str(error)), 422
    finally:
        if 'path' in locals(): Path(path).unlink(missing_ok=True)

@admin_bp.get('/backups')
@roles_required('ADMIN')
def backups():
    folder = Path(current_app.config.get('BACKUP_FOLDER', Path(current_app.instance_path) / 'backups'))
    items = []
    for manifest in sorted(folder.glob('*.json'), key=lambda item: item.stat().st_mtime, reverse=True)[:100]:
        try:
            payload = json.loads(manifest.read_text(encoding='utf-8'))
            sql = manifest.with_suffix('.sql')
            payload.update({'verified': sql.exists(), 'manifest': manifest.name})
            items.append(payload)
        except (OSError, ValueError):
            continue
    return items

@admin_bp.post('/backups')
@roles_required('ADMIN')
def create_backup_route():
    from ..services.backup import create_backup
    try:
        result = create_backup(current_app)
    except (OSError, RuntimeError) as error:
        return jsonify(message=str(error)), 503
    audit(current_user().id, 'CREATE', 'DATABASE_BACKUP', result['file'], {'sha256': result['sha256'], 'size_bytes': result['size_bytes']})
    db.session.commit()
    return result, 201

@admin_bp.get("/catalogs")
@auth_required
def catalogs():
    query=db.select(Catalog).order_by(Catalog.category,Catalog.label);category=request.args.get("category")
    if category:query=query.where(Catalog.category==category)
    return [{"id":r.id,"category":r.category,"code":r.code,"label":r.label,"active":r.active} for r in db.session.scalars(query).all()]

@admin_bp.post("/catalogs")
@roles_required("ADMIN")
def create_catalog():
    p=data();r=Catalog(category=required(p.get("category"),"category",2,80).upper(),code=required(p.get("code"),"code",1,80).upper(),label=required(p.get("label"),"label",2,150));db.session.add(r);db.session.flush();audit(current_user().id,"CREATE","CATALOG",r.id);db.session.commit();return {"id":r.id,"category":r.category,"code":r.code,"label":r.label,"active":r.active},201

@admin_bp.get("/users")
@roles_required("ADMIN")
def users():return [{**r.public(),"created_at":r.created_at.isoformat(),"updated_at":r.updated_at.isoformat()} for r in db.session.scalars(db.select(User).where(User.role != 'RESEARCHER').order_by(User.full_name)).all()]

@admin_bp.post("/users")
@roles_required("ADMIN")
def create_user():
    p=data();password=required(p.get("password"),"password")
    if not is_strong_password(password):raise ValidationFailure("La contraseña debe tener al menos 12 caracteres e incluir mayúscula, minúscula, número y símbolo.")
    role=p.get("role");
    if role not in {"ADMIN","INVENTORY","VIEWER"}:raise ValidationFailure("Rol operativo no permitido. Investigación se administra por separado.")
    row=User(username=required(p.get("username"),"username",3,50),email=required(p.get("email"),"email",3,150),full_name=required(p.get("fullName"),"fullName",3,150),password_hash=generate_password_hash(password,method="scrypt"),role=role)
    db.session.add(row);db.session.flush();audit(current_user().id,"CREATE","USER",row.id,{"username":row.username,"role":role});db.session.commit();return row.public(),201

@admin_bp.post("/users/<user_id>/reset-password")
@roles_required("ADMIN")
def reset_password(user_id):
    row=db.session.get(User,user_id)
    if not row:return jsonify(message="Usuario no encontrado."),404
    if row.role == 'RESEARCHER': return jsonify(message='Esta cuenta tiene un procedimiento independiente de recuperación.'), 403
    password=required(data().get("temporaryPassword"),"temporaryPassword")
    if not is_strong_password(password):raise ValidationFailure("La contraseña temporal no cumple la política.")
    row.password_hash=generate_password_hash(password,method="scrypt");row.must_change_password=True;row.password_changed_at=None;row.session_version += 1;audit(current_user().id,"RESET_PASSWORD","USER",row.id);db.session.commit();return "",204


@admin_bp.patch('/users/<user_id>')
@roles_required('ADMIN')
def update_user(user_id):
    row = db.session.get(User, user_id); payload = data()
    if not row: return jsonify(message='Usuario no encontrado.'), 404
    if row.role == 'RESEARCHER': return jsonify(message='Cuenta fuera de la administración operativa.'), 403
    role = payload.get('role', row.role); active = payload.get('active', row.active)
    if role not in {'ADMIN', 'INVENTORY', 'VIEWER'} or type(active) is not bool:
        raise ValidationFailure('Rol o estado no permitido.')
    if row.id == current_user().id and (not active or role != 'ADMIN'):
        return jsonify(message='No puede quitarse su propio acceso administrativo.'), 409
    row.role = role; row.active = active; row.session_version += 1
    audit(current_user().id, 'UPDATE_ACCESS', 'USER', row.id, {'role': role, 'active': active})
    db.session.commit(); return row.public()

@admin_bp.get("/audit-logs")
@roles_required("ADMIN")
def logs():
    research_entities = ['OBSERVATION', 'REPORT_TRIAL', 'RESEARCH_SAMPLE', 'RESEARCH_PHASE', 'PATRIMONIAL', 'CENSUS', 'RESEARCH_ACCOUNT', 'GUIDE_STUDY']
    rows=db.session.scalars(db.select(AuditLog).where(~AuditLog.entity_type.in_(research_entities),
         (AuditLog.user_id.is_(None) | ~AuditLog.user_id.in_(db.select(User.id).where(User.role == 'RESEARCHER'))))
         .order_by(AuditLog.created_at.desc()).limit(500)).all()
    return [{"id":r.id,"user_id":r.user_id,"action":r.action,"entity_type":r.entity_type,"entity_id":r.entity_id,"details":r.details,"ip_address":r.ip_address,"created_at":r.created_at.isoformat()} for r in rows]
