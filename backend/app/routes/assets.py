from datetime import datetime, timezone

import csv
import io
from flask import Blueprint, Response, jsonify, request
from sqlalchemy import func, or_

from ..extensions import db
from ..models import Asset, AssetGroup, AssetGroupMember, Movement, InventorySession, MaintenancePlan
from ..security import auth_required, current_user, roles_required
from ..services.audit import audit
from ..validation import ValidationFailure, data, required, sbn

assets_bp = Blueprint("assets", __name__)
ASSET_TYPES = {"TYPE_1", "TYPE_2", "TYPE_3", "LAPTOP", "PRINTER", "ALL_IN_ONE", "MONITOR", "KEYBOARD", "CPU"}
# Fuente: Excel patrimonial, 02_Base Consolidada, columnas Situación y Condición.
# En el libro Situación describe conservación; Condición describe operatividad.
STATUSES = {"OPERATIVO", "MANTENIMIENTO", "BAJA", "NO_OPERATIVO", "INOPERATIVO", "SIN_DATO"}
CONDITIONS = {"BUENO", "REGULAR", "MALO", "NUEVO", "FALTANTE"}


def maintenance_dict(row):
    asset = db.session.get(Asset, row.asset_id)
    return {"id": row.id, "assetId": row.asset_id, "sbn": asset.sbn if asset else None, "description": asset.description if asset else None,
            "planType": row.plan_type, "dueDate": row.due_date.isoformat(), "status": row.status,
            "provider": row.provider, "responsible": row.responsible, "cost": row.cost,
            "completedAt": row.completed_at.isoformat() if row.completed_at else None, "notes": row.notes}


@assets_bp.get('/maintenance')
@auth_required
def maintenance_list():
    from datetime import datetime, timezone
    query = db.select(MaintenancePlan).order_by(MaintenancePlan.due_date)
    rows = db.session.scalars(query.limit(500)).all()
    now = datetime.now(timezone.utc)
    result = []
    for row in rows:
        item = maintenance_dict(row)
        item['overdue'] = row.status == 'PLANNED' and row.due_date < now
        result.append(item)
    return result


@assets_bp.post('/maintenance')
@roles_required('ADMIN')
def create_maintenance():
    from datetime import datetime
    payload = data(); asset = db.session.get(Asset, payload.get('assetId'))
    if not asset: return jsonify(message='Activo no encontrado.'), 404
    try: due_date = datetime.fromisoformat(required(payload.get('dueDate'), 'dueDate'))
    except ValueError as error: raise ValidationFailure('dueDate debe ser una fecha ISO válida.') from error
    status = payload.get('status', 'PLANNED')
    if status not in {'PLANNED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED'}: raise ValidationFailure('Estado de mantenimiento no permitido.')
    row = MaintenancePlan(asset_id=asset.id, plan_type=payload.get('planType', 'PREVENTIVE'), due_date=due_date,
                          status=status, provider=payload.get('provider'), responsible=payload.get('responsible'),
                          cost=payload.get('cost'), notes=payload.get('notes'))
    db.session.add(row); db.session.flush(); audit(current_user().id, 'CREATE', 'MAINTENANCE_PLAN', row.id); db.session.commit()
    return maintenance_dict(row), 201


@assets_bp.patch('/maintenance/<plan_id>')
@roles_required('ADMIN')
def update_maintenance(plan_id):
    from datetime import datetime, timezone
    row = db.session.get(MaintenancePlan, plan_id)
    if not row: return jsonify(message='Plan de mantenimiento no encontrado.'), 404
    payload = data()
    if 'status' in payload and payload['status'] not in {'PLANNED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED'}: raise ValidationFailure('Estado no permitido.')
    for key, field in [('status', 'status'), ('provider', 'provider'), ('responsible', 'responsible'), ('notes', 'notes'), ('cost', 'cost')]:
        if key in payload: setattr(row, field, payload[key])
    if 'dueDate' in payload:
        try: row.due_date = datetime.fromisoformat(payload['dueDate'])
        except ValueError as error: raise ValidationFailure('dueDate debe ser una fecha ISO válida.') from error
    if row.status == 'COMPLETED' and not row.completed_at: row.completed_at = datetime.now(timezone.utc)
    audit(current_user().id, 'UPDATE', 'MAINTENANCE_PLAN', row.id, {'status': row.status}); db.session.commit()
    return maintenance_dict(row)


def apply_asset_payload(asset, payload):
    asset.sbn = sbn(payload.get("sbn")); asset.asset_type = required(payload.get("assetType"), "assetType")
    asset.description = required(payload.get("description"), "description", 3, 250); asset.site = required(payload.get("site"), "site", 2, 150)
    if asset.asset_type not in ASSET_TYPES: raise ValidationFailure("Tipo de activo no permitido.")
    asset.status = payload.get("status", "OPERATIVO"); asset.condition = payload.get("condition", "BUENO")
    if asset.status not in STATUSES or asset.condition not in CONDITIONS: raise ValidationFailure("Estado o condición no permitidos.")
    mapping = {"internalCode": "internal_code", "brand": "brand", "model": "model", "serialNumber": "serial_number",
               "executingUnit": "executing_unit", "building": "building", "floor": "floor", "room": "room",
               "organizationalUnit": "organizational_unit", "responsiblePerson": "responsible_person",
               "thirdPartyUser": "third_party_user", "processor": "processor", "memory": "memory", "storage": "storage",
               "operatingSystem": "operating_system", "notes": "notes"}
    for source, target in mapping.items():
        value = str(payload[source]).strip() if payload.get(source) else None
        limit = getattr(Asset.__table__.columns[target].type, 'length', None)
        if limit and value and len(value) > limit: raise ValidationFailure(f'{source} admite hasta {limit} caracteres.')
        setattr(asset, target, value)
    software = payload.get("installedSoftware", [])
    if not isinstance(software, list): raise ValidationFailure("installedSoftware debe ser una lista.")
    asset.installed_software = [required(item, "software", 1, 150) for item in software]
    for source, target in {"recordComplete": "record_complete", "recordConsistent": "record_consistent",
                           "correctlyRegistered": "correctly_registered", "recordUpdated": "record_updated",
                           "barcodeVerified": "barcode_verified"}.items(): setattr(asset, target, bool(payload.get(source, False)))
    if asset.barcode_verified: asset.last_verified_at = datetime.now(timezone.utc)


def movement_dict(row):
    return {"id": row.id, "asset_id": row.asset_id, "movement_type": row.movement_type, "previous_site": row.previous_site,
            "new_site": row.new_site, "previous_responsible": row.previous_responsible, "new_responsible": row.new_responsible,
            "reason": row.reason, "support_document": row.support_document, "status": row.status,
            "requested_at": row.requested_at.isoformat() if row.requested_at else None,
            "approved_at": row.approved_at.isoformat() if row.approved_at else None,
            "delivered_at": row.delivered_at.isoformat() if row.delivered_at else None,
            "rejection_reason": row.rejection_reason, "created_at": row.created_at.isoformat()}


@assets_bp.get("/assets")
@auth_required
def list_assets():
    search = request.args.get("search", "").strip(); asset_type = request.args.get("type", "").strip(); status = request.args.get("status", "").strip(); site = request.args.get("site", "").strip()
    page = max(1, request.args.get("page", 1, type=int)); size = min(500, max(1, request.args.get("pageSize", 25, type=int)))
    from ..security import scoped_assets
    query = scoped_assets(db.select(Asset))
    if search:
        term = f"%{search}%"; query = query.where(or_(Asset.sbn.like(term), Asset.serial_number.like(term), Asset.description.like(term), Asset.responsible_person.like(term)))
    if asset_type: query = query.where(Asset.asset_type == asset_type)
    if status: query = query.where(Asset.status == status)
    if site: query = query.where(Asset.site == site)
    if request.args.get('ungrouped') == '1':
        query = query.where(Asset.asset_type.in_(['ALL_IN_ONE', 'TYPE_1', 'TYPE_2', 'TYPE_3', 'MONITOR', 'KEYBOARD', 'CPU']), ~Asset.group_membership.has())
    total = db.session.scalar(db.select(func.count()).select_from(query.subquery()))
    rows = db.session.scalars(query.order_by(Asset.updated_at.desc(), Asset.sbn).offset((page - 1) * size).limit(size)).all()
    return {"items": [row.api_dict() for row in rows], "total": total, "page": page, "pageSize": size}


@assets_bp.get('/assets.csv')
@auth_required
def assets_csv():
    from ..security import scoped_assets
    search = request.args.get('search', '').strip(); asset_type = request.args.get('type', '').strip(); status = request.args.get('status', '').strip()
    query = scoped_assets(db.select(Asset))
    if search:
        term = f"%{search}%"; query = query.where(or_(Asset.sbn.like(term), Asset.serial_number.like(term), Asset.description.like(term), Asset.responsible_person.like(term)))
    if asset_type: query = query.where(Asset.asset_type == asset_type)
    if status: query = query.where(Asset.status == status)
    rows = db.session.scalars(query.order_by(Asset.sbn).limit(10000)).all()
    output = io.StringIO(); writer = csv.writer(output)
    fields = ['sbn', 'asset_type', 'description', 'brand', 'model', 'serial_number', 'site', 'building', 'floor', 'room', 'status', 'condition', 'responsible_person', 'last_verified_at']
    writer.writerow(fields)
    for row in rows:
        writer.writerow([getattr(row, field).isoformat() if field == 'last_verified_at' and getattr(row, field) else getattr(row, field) for field in fields])
    return Response('\ufeff' + output.getvalue(), mimetype='text/csv; charset=utf-8', headers={'Content-Disposition': 'attachment; filename=inventario_activos.csv'})


@assets_bp.get("/assets/sbn/<value>")
@auth_required
def by_sbn(value):
    asset = db.session.execute(db.select(Asset).where(Asset.sbn == sbn(value))).scalar_one_or_none()
    if not asset: return jsonify(message=f"No se encontró un activo con SBN {value}.", inventoryStatus="NOT_FOUND"), 404
    from ..security import ensure_asset_access
    ensure_asset_access(asset)
    result = asset.api_dict()
    if asset.group_membership and current_user().role == 'ADMIN':
        result["assetGroup"] = asset.group_membership.group.api_dict()
    return result


@assets_bp.get("/assets/<asset_id>")
@auth_required
def get_asset(asset_id):
    asset = db.session.get(Asset, asset_id)
    if not asset: return jsonify(message="Activo no encontrado."), 404
    from ..security import ensure_asset_access
    ensure_asset_access(asset)
    result = asset.api_dict(); result["movements"] = [movement_dict(row) for row in sorted(asset.movements, key=lambda item: item.created_at, reverse=True)] if current_user().role == 'ADMIN' else []
    return result


@assets_bp.post("/assets")
@roles_required("ADMIN")
def create_asset():
    asset = Asset(); apply_asset_payload(asset, data()); db.session.add(asset); db.session.flush()
    audit(current_user().id, "CREATE", "ASSET", asset.id, {"sbn": asset.sbn}); db.session.commit(); return asset.api_dict(), 201


@assets_bp.put("/assets/<asset_id>")
@roles_required("ADMIN")
def update_asset(asset_id):
    asset = db.session.get(Asset, asset_id)
    if not asset: return jsonify(message="Activo no encontrado."), 404
    payload = data()
    if payload.get('version') != asset.version: return jsonify(message='El activo cambió. Recargue la ficha antes de guardar.'), 409
    reason = required(payload.get('correctionReason'), 'motivo de corrección', 5, 1000)
    before = asset.api_dict()
    apply_asset_payload(asset, payload)
    audit(current_user().id, 'UPDATE', 'ASSET', asset.id, {'before': before, 'after': asset.api_dict(), 'reason': reason})
    db.session.commit(); return asset.api_dict()


@assets_bp.delete("/assets/<asset_id>")
@roles_required("ADMIN")
def delete_asset(asset_id):
    asset = db.session.get(Asset, asset_id)
    if not asset: return jsonify(message="Activo no encontrado."), 404
    return jsonify(message='Use el estado BAJA para conservar la trazabilidad del activo. No se permite eliminar físicamente.'), 409


@assets_bp.get("/dashboard")
@auth_required
def dashboard():
    from datetime import datetime, timezone
    total = db.session.scalar(db.select(func.count(Asset.id))) or 0
    by_status = dict(db.session.execute(db.select(Asset.status, func.count()).group_by(Asset.status)).all())
    complete_consistent = db.session.scalar(db.select(func.count(Asset.id)).where(Asset.record_complete.is_(True), Asset.record_consistent.is_(True))) or 0
    barcode_verified = db.session.scalar(db.select(func.count(Asset.id)).where(Asset.barcode_verified.is_(True))) or 0
    updated = db.session.scalar(db.select(func.count(Asset.id)).where(Asset.record_updated.is_(True))) or 0
    by_type = [{"type": key, "total": value} for key, value in db.session.execute(db.select(Asset.asset_type, func.count()).group_by(Asset.asset_type)).all()]
    by_site = [{"site": key, "total": value} for key, value in db.session.execute(db.select(Asset.site, func.count()).group_by(Asset.site)).all()]
    recent = db.session.scalars(db.select(Asset).order_by(Asset.updated_at.desc()).limit(5)).all()
    ungrouped = db.session.scalar(db.select(func.count(Asset.id)).where(Asset.asset_type.in_(["ALL_IN_ONE", "MONITOR", "KEYBOARD", "CPU", "TYPE_1", "TYPE_2", "TYPE_3"]), ~Asset.group_membership.has())) or 0
    incomplete_groups = sum(not group.api_dict()["complete"] for group in db.session.scalars(db.select(AssetGroup)).all())
    def missing(field):
        column = getattr(Asset, field)
        return db.session.scalars(db.select(Asset).where(or_(column.is_(None), column == "")).order_by(Asset.sbn).limit(100)).all()
    missing_location = missing("site")
    missing_responsible = missing("responsible_person")
    missing_serial = missing("serial_number")
    open_sessions = db.session.scalars(db.select(InventorySession).where(InventorySession.status == "OPEN").order_by(InventorySession.started_at.desc()).limit(100)).all()
    overdue_maintenance = db.session.scalars(db.select(MaintenancePlan).where(MaintenancePlan.status == "PLANNED", MaintenancePlan.due_date < datetime.now(timezone.utc)).order_by(MaintenancePlan.due_date).limit(100)).all()
    def alert(code, label, rows, severity="warning"):
        return {"code": code, "label": label, "severity": severity, "count": len(rows),
                "items": [{"id": getattr(row, "id", None), "sbn": getattr(row, "sbn", None),
                            "name": getattr(row, "name", None), "site": getattr(row, "site", None)} for row in rows]}
    alerts = [
        alert("MISSING_LOCATION", "Activos sin ubicación", missing_location),
        alert("MISSING_RESPONSIBLE", "Activos sin responsable", missing_responsible),
        alert("MISSING_SERIAL", "Activos sin número de serie", missing_serial),
        alert("UNGROUPED_COMPONENTS", "Componentes sin agrupar", db.session.scalars(db.select(Asset).where(Asset.asset_type.in_(["ALL_IN_ONE", "MONITOR", "KEYBOARD", "CPU", "TYPE_1", "TYPE_2", "TYPE_3"]), ~Asset.group_membership.has()).order_by(Asset.sbn).limit(100)).all()),
        alert("OPEN_INVENTORY_SESSIONS", "Jornadas con pendientes", open_sessions),
        {"code": "DUPLICATE_SBN", "label": "Registros duplicados", "severity": "critical", "count": 0, "items": [], "note": "SBN tiene restricción UNIQUE; revisar importaciones rechazadas."},
        alert("MAINTENANCE_OVERDUE", "Mantenimiento vencido", overdue_maintenance, "critical"),
    ]
    return {"totals": {"total": total, "operational": by_status.get("OPERATIVO", 0),
                        "complete_consistent": complete_consistent, "barcode_verified": barcode_verified, "updated": updated},
            "grouping": {"ungroupedComponents": ungrouped, "incompleteGroups": incomplete_groups},
            "byType": by_type, "bySite": by_site, "recent": [row.api_dict() for row in recent],
            "alerts": alerts, "alertTotal": sum(item["count"] for item in alerts)}


@assets_bp.get("/asset-groups")
@auth_required
def list_groups():
    return [group.api_dict() for group in db.session.scalars(db.select(AssetGroup).order_by(AssetGroup.code)).all()]


@assets_bp.post("/asset-groups")
@roles_required("ADMIN")
def create_group():
    payload = data(); group_type = payload.get("groupType")
    if group_type not in {"ALL_IN_ONE", "TYPE_2", "TYPE_3"}: raise ValidationFailure("Tipo de agrupación no permitido.")
    group = AssetGroup(code=required(payload.get("code"), "code", 3, 30).upper(), group_type=group_type,
                       name=required(payload.get("name"), "name", 3, 150), site=required(payload.get("site"), "site", 2, 150),
                       responsible_person=payload.get("responsiblePerson") or None)
    db.session.add(group); db.session.flush(); audit(current_user().id, "CREATE", "ASSET_GROUP", group.id, {"code": group.code}); db.session.commit()
    return group.api_dict(), 201


@assets_bp.post("/asset-groups/<group_id>/members")
@roles_required("ADMIN")
def add_group_member(group_id):
    group = db.session.get(AssetGroup, group_id); payload = data()
    if not group: return jsonify(message="Agrupación no encontrada."), 404
    asset = db.session.execute(db.select(Asset).where(Asset.sbn == sbn(payload.get("sbn")))).scalar_one_or_none()
    if not asset: return jsonify(message="El SBN indicado no está inventariado."), 404
    role = required(payload.get("componentRole"), "componentRole", 2, 30)
    allowed = {"ALL_IN_ONE": {"INTEGRATED_UNIT", "KEYBOARD"}, "TYPE_2": {"MONITOR", "KEYBOARD", "CPU"}, "TYPE_3": {"MONITOR", "KEYBOARD", "CPU"}}[group.group_type]
    if role not in allowed: raise ValidationFailure("El componente no corresponde al tipo de agrupación.")
    expected_type = {"INTEGRATED_UNIT": "ALL_IN_ONE", "MONITOR": "MONITOR", "KEYBOARD": "KEYBOARD", "CPU": "CPU"}[role]
    compatible = {expected_type}
    if role == 'INTEGRATED_UNIT': compatible.add('TYPE_1')
    if role == 'CPU': compatible.add(group.group_type)
    if asset.asset_type not in compatible:
        raise ValidationFailure(f"El activo es {asset.asset_type} y no puede ocupar la función {role}.")
    if asset.group_membership: return jsonify(message=f"El activo ya pertenece al grupo {asset.group_membership.group.code}."), 409
    if any(member.component_role == role for member in group.members):
        return jsonify(message=f"El grupo {group.code} ya tiene un componente asignado como {role}. Cree un grupo nuevo o seleccione una función faltante."), 409
    member = AssetGroupMember(group=group, asset=asset, component_role=role); db.session.add(member)
    audit(current_user().id, "GROUP", "ASSET", asset.id, {"group": group.code, "role": role}); db.session.commit()
    return group.api_dict(), 201


@assets_bp.get("/movements")
@auth_required
def movements():
    asset_id = request.args.get("assetId"); query = db.select(Movement).order_by(Movement.created_at.desc())
    if asset_id: query = query.where(Movement.asset_id == asset_id)
    return [movement_dict(row) for row in db.session.scalars(query.limit(500)).all()]


@assets_bp.get("/movements.csv")
@roles_required("ADMIN")
def movements_csv():
    rows = db.session.scalars(db.select(Movement).order_by(Movement.created_at.desc()).limit(5000)).all()
    output = io.StringIO(); writer = csv.writer(output)
    writer.writerow(['id', 'asset_id', 'movement_type', 'status', 'previous_site', 'new_site',
                     'previous_responsible', 'new_responsible', 'reason', 'support_document',
                     'requested_at', 'approved_at', 'delivered_at', 'rejection_reason', 'created_at'])
    for row in rows:
        item = movement_dict(row)
        writer.writerow([item.get(key) for key in ('id', 'asset_id', 'movement_type', 'status', 'previous_site', 'new_site',
                                                   'previous_responsible', 'new_responsible', 'reason', 'support_document',
                                                   'requested_at', 'approved_at', 'delivered_at', 'rejection_reason', 'created_at')])
    return Response('\ufeff' + output.getvalue(), mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename=movimientos.csv'})


@assets_bp.post("/movements")
@roles_required("ADMIN")
def create_movement():
    payload = data(); asset = db.session.get(Asset, required(payload.get("assetId"), "assetId"))
    if not asset: return jsonify(message="Activo no encontrado."), 404
    row = Movement(asset_id=asset.id, movement_type=required(payload.get("movementType"), "movementType", 2, 100),
                   previous_site=asset.site, new_site=payload.get("newSite") or asset.site,
                   previous_responsible=asset.responsible_person, new_responsible=payload.get("newResponsible") or asset.responsible_person,
                   reason=required(payload.get("reason"), "reason", 3, 1000), support_document=payload.get("supportDocument") or None,
                   performed_by=current_user().id)
    db.session.add(row); db.session.flush()
    audit(current_user().id, "CREATE", "MOVEMENT", row.id, {"assetId": asset.id}); db.session.commit(); return movement_dict(row), 201


def movement_or_404(movement_id):
    row = db.session.get(Movement, movement_id)
    if not row: return None, (jsonify(message="Movimiento no encontrado."), 404)
    return row, None


@assets_bp.post("/movements/<movement_id>/approve")
@roles_required("ADMIN")
def approve_movement(movement_id):
    row, error = movement_or_404(movement_id)
    if error: return error
    if row.status != 'REQUESTED': return jsonify(message="Solo se pueden aprobar solicitudes pendientes."), 409
    row.status = 'APPROVED'; row.approved_by = current_user().id; row.approved_at = datetime.now(timezone.utc)
    audit(current_user().id, 'APPROVE', 'MOVEMENT', row.id); db.session.commit(); return movement_dict(row)


@assets_bp.post("/movements/<movement_id>/reject")
@roles_required("ADMIN")
def reject_movement(movement_id):
    row, error = movement_or_404(movement_id)
    if error: return error
    if row.status != 'REQUESTED': return jsonify(message="Solo se pueden rechazar solicitudes pendientes."), 409
    reason = required(data().get('reason'), 'reason', 5, 1000)
    row.status = 'REJECTED'; row.rejection_reason = reason
    audit(current_user().id, 'REJECT', 'MOVEMENT', row.id, {'reason': reason}); db.session.commit(); return movement_dict(row)


@assets_bp.post("/movements/<movement_id>/deliver")
@roles_required("ADMIN")
def deliver_movement(movement_id):
    row, error = movement_or_404(movement_id)
    if error: return error
    if row.status != 'APPROVED': return jsonify(message="Solo se pueden entregar movimientos aprobados."), 409
    asset = db.session.get(Asset, row.asset_id)
    asset.site = row.new_site or asset.site; asset.responsible_person = row.new_responsible or asset.responsible_person
    row.status = 'DELIVERED'; row.delivered_at = datetime.now(timezone.utc)
    audit(current_user().id, 'DELIVER', 'MOVEMENT', row.id, {'assetId': asset.id}); db.session.commit(); return movement_dict(row)
