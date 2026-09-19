from datetime import datetime, timezone
from flask import Blueprint, abort, jsonify
from ..extensions import db
from ..models import Asset, InventoryCheck, InventorySession, InventoryAssignment, User, Evidence
from ..security import auth_required, current_user, roles_required
from ..services.audit import audit
from ..validation import ValidationFailure, data, required, sbn

inventory_bp = Blueprint('inventory', __name__)


def accessible_session(session_id, lock=False):
    query = db.select(InventorySession).where(InventorySession.id == session_id)
    if lock: query = query.with_for_update()
    row = db.session.scalar(query)
    if not row: abort(404)
    if current_user().role != 'ADMIN' and not db.session.get(InventoryAssignment, (session_id, current_user().id)):
        abort(403)
    return row


def session_dict(row):
    assigned = db.session.scalars(db.select(InventoryAssignment.user_id).where(InventoryAssignment.session_id == row.id)).all()
    return {'id': row.id, 'name': row.name, 'phase': row.phase, 'site': row.site, 'status': row.status,
            'assignedUsers': assigned if current_user().role == 'ADMIN' else [],
            'started_at': row.started_at.isoformat(), 'closed_at': row.closed_at.isoformat() if row.closed_at else None,
            'checked_count': db.session.query(InventoryCheck).filter_by(session_id=row.id).count()}


def check_dict(row):
    return {'id': row.id, 'asset_id': row.asset_id, 'result': row.result, 'notes': row.notes,
            'version': row.version, 'checked_by': row.checked_by, 'checked_at': row.checked_at.isoformat(),
            'scanned_sbn': row.scanned_sbn,
            'evidence': [e.id for e in db.session.scalars(db.select(Evidence).where(Evidence.check_id == row.id)).all()]}


@inventory_bp.get('/inventory-sessions')
@auth_required
def sessions():
    query = db.select(InventorySession)
    if current_user().role != 'ADMIN':
        query = query.join(InventoryAssignment).where(InventoryAssignment.user_id == current_user().id)
    return [session_dict(row) for row in db.session.scalars(query.order_by(InventorySession.started_at.desc())).all()]


@inventory_bp.get('/inventory-sites')
@roles_required('ADMIN')
def sites():
    return list(db.session.scalars(db.select(Asset.site).where(Asset.site != '').distinct().order_by(Asset.site)))


@inventory_bp.post('/inventory-sessions')
@roles_required('ADMIN')
def create_session():
    payload = data(); site = required(payload.get('site'), 'sede', 2, 150)
    if not db.session.scalar(db.select(Asset.id).where(Asset.site == site).limit(1)):
        raise ValidationFailure('La sede no existe en el inventario.')
    users = payload.get('assignedUsers', [])
    if not isinstance(users, list) or not users: raise ValidationFailure('Asigne al menos un usuario general.')
    for user_id in users:
        user = db.session.get(User, user_id)
        if not user or not user.active or user.role != 'INVENTORY': raise ValidationFailure('Usuario general no válido.')
    row = InventorySession(name=required(payload.get('name'), 'nombre', 3, 150), phase='OPERATIVO', site=site, created_by=current_user().id)
    db.session.add(row); db.session.flush()
    for user_id in set(users): db.session.add(InventoryAssignment(session_id=row.id, user_id=user_id))
    audit(current_user().id, 'CREATE', 'INVENTORY_SESSION', row.id, {'site': site, 'assignedUsers': users})
    db.session.commit(); return session_dict(row), 201


@inventory_bp.get('/inventory-sessions/<session_id>')
@auth_required
def get_session(session_id):
    row = accessible_session(session_id)
    checks = db.session.execute(db.select(InventoryCheck, Asset).join(Asset).where(InventoryCheck.session_id == session_id)
                                .order_by(InventoryCheck.checked_at.desc())).all()
    total = db.session.query(Asset).filter_by(site=row.site).count()
    return {**session_dict(row), 'total': total, 'pending': max(0, total - len(checks)),
            'checks': [{**check_dict(c), 'sbn': a.sbn, 'description': a.description, 'site': a.site} for c, a in checks]}


@inventory_bp.post('/inventory-sessions/<session_id>/checks')
@roles_required('ADMIN', 'INVENTORY')
def check(session_id):
    payload = data(); session = accessible_session(session_id, lock=True)
    if session.status != 'OPEN': return jsonify(message='La jornada está cerrada.'), 409
    code = sbn(payload.get('sbn'))
    asset = db.session.scalar(db.select(Asset).where(Asset.sbn == code))
    if not asset: return jsonify(message='El código no está inventariado. Informe al administrador.'), 404
    if asset.site != session.site: return jsonify(message='El activo está registrado en otra sede. Solicite revisión al administrador.'), 409
    result = payload.get('result')
    if result not in {'MATCH', 'MISMATCH', 'NOT_FOUND', 'NOT_APPLICABLE'}: raise ValidationFailure('Resultado no permitido.')
    row = db.session.scalar(db.select(InventoryCheck).where(InventoryCheck.session_id == session_id, InventoryCheck.asset_id == asset.id))
    previous = check_dict(row) if row else None
    if row:
        if payload.get('version') != row.version: return jsonify(message='Este hallazgo fue modificado. Recargue para revisarlo.'), 409
        reason = required(payload.get('correctionReason'), 'motivo de corrección', 5, 1000)
    else:
        if payload.get('version') not in (None, 0): return jsonify(message='La versión no corresponde al registro.'), 409
        reason = None
        row = InventoryCheck(session_id=session_id, asset_id=asset.id); db.session.add(row)
    notes = str(payload.get('notes') or '').strip()
    if len(notes) > 1000: raise ValidationFailure('La observación admite hasta 1000 caracteres.')
    if result != 'MATCH' and not notes: raise ValidationFailure('Describa el hallazgo.')
    row.result = result; row.scanned_sbn = code; row.notes = notes or None; row.checked_by = current_user().id
    audit(current_user().id, 'UPSERT', 'INVENTORY_CHECK', asset.id,
          {'sessionId': session_id, 'before': previous, 'result': result, 'notes': notes, 'correctionReason': reason})
    db.session.commit(); return check_dict(row), 201


@inventory_bp.post('/inventory-sessions/<session_id>/close')
@roles_required('ADMIN')
def close(session_id):
    row = accessible_session(session_id, lock=True)
    if row.status != 'OPEN': return jsonify(message='La jornada ya está cerrada.'), 409
    row.status = 'CLOSED'; row.closed_at = datetime.now(timezone.utc)
    audit(current_user().id, 'CLOSE', 'INVENTORY_SESSION', row.id); db.session.commit()
    return session_dict(row)


@inventory_bp.post('/inventory-checks/<check_id>/evidence')
@roles_required('ADMIN', 'INVENTORY')
def upload_evidence(check_id):
    import io
    import uuid
    import warnings
    from pathlib import Path
    from flask import current_app, request
    from PIL import Image, ImageOps, UnidentifiedImageError
    check = db.session.get(InventoryCheck, check_id)
    if not check: abort(404)
    session = accessible_session(check.session_id, lock=True)
    if session.status != 'OPEN': return jsonify(message='La jornada está cerrada.'), 409
    if db.session.query(Evidence).filter_by(check_id=check.id).count() >= 3:
        return jsonify(message='Máximo tres fotografías por hallazgo.'), 409
    file = request.files.get('photo')
    if not file: raise ValidationFailure('Seleccione una fotografía JPEG o PNG.')
    raw = file.read(5 * 1024 * 1024 + 1)
    if len(raw) > 5 * 1024 * 1024: raise ValidationFailure('Máximo 5 MB por fotografía.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in {'JPEG', 'PNG'} or image.width * image.height > 25000000:
                    raise ValidationFailure('Formato o tamaño de imagen no permitido.')
                clean = ImageOps.exif_transpose(image).convert('RGB')
                clean.thumbnail((1920, 1920))
                output = io.BytesIO(); clean.save(output, format='JPEG', quality=85)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValidationFailure('No se pudo validar la imagen.')
    # Pillow reexporta sin EXIF ni ubicación GPS. Almacén fuera del frontend.
    folder = Path(current_app.config['UPLOAD_FOLDER']); folder.mkdir(parents=True, exist_ok=True)
    filename = uuid.uuid4().hex + '.jpg'; target = folder / filename
    try:
        target.write_bytes(output.getvalue())
        row = Evidence(check_id=check.id, uploaded_by=current_user().id, filename=filename)
        db.session.add(row); db.session.flush()
        audit(current_user().id, 'UPLOAD', 'INVENTORY_EVIDENCE', row.id, {'checkId': check.id})
        db.session.commit()
    except Exception:
        db.session.rollback(); target.unlink(missing_ok=True); raise
    return {'id': row.id}, 201


@inventory_bp.get('/inventory-evidence/<evidence_id>')
@auth_required
def evidence_file(evidence_id):
    from flask import current_app, send_from_directory
    row = db.session.get(Evidence, evidence_id)
    if not row: abort(404)
    check = db.session.get(InventoryCheck, row.check_id)
    accessible_session(check.session_id)
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], row.filename, mimetype='image/jpeg')
