"""Investigación separada de la administración operativa.

Fuente metodológica: Excel entregado, 05_Vinculo Guias; alcance censal
Libros y El Comercio confirmado por el usuario. Las evidencias de inventario
no se convierten automáticamente en resultados de las seis guías.
"""
from datetime import datetime, timezone
from flask import Blueprint, jsonify, Response
from ..extensions import db
from ..models import Asset, ResearchSample, CensusSnapshot, ResearchPhase, Observation, AuditLog, InventoryCheck
from ..security import roles_required, current_user
from ..services.audit import audit
from ..services.research import csv_response
from ..validation import data, required

study_bp = Blueprint('study', __name__)


def freeze_census():
    if db.session.scalar(db.select(CensusSnapshot.asset_id).limit(1)): return
    for selected, asset in db.session.execute(db.select(ResearchSample, Asset).join(Asset)).all():
        db.session.add(CensusSnapshot(asset_id=asset.id, sample_code=selected.sample_code, data=asset.api_dict()))
    audit(current_user().id, 'FREEZE', 'CENSUS', details={'method': 'CENSUS'})
    db.session.flush()


def open_phase(phase):
    from ..validation import ValidationFailure
    if phase not in {'PRETEST', 'POSTTEST'}: raise ValidationFailure('Fase no válida.')
    from ..models import ResearchSettings
    db.session.scalar(db.select(ResearchSettings).where(ResearchSettings.id == 1).with_for_update())
    # Misma fila bloqueada para serializar mediciones y cierre.
    row = db.session.scalar(db.select(ResearchPhase).where(ResearchPhase.phase == phase).with_for_update())
    if row and row.status != 'OPEN': raise ValidationFailure('La fase está cerrada. No admite modificaciones.')
    if row is None:
        row = ResearchPhase(phase=phase); db.session.add(row); db.session.flush()
    return row


@study_bp.get('/research/phases')
@roles_required('RESEARCHER')
def phases():
    rows = {r.phase: r for r in db.session.scalars(db.select(ResearchPhase)).all()}
    return {'frozen': bool(db.session.scalar(db.select(CensusSnapshot.asset_id).limit(1))),
            'phases': [{'phase': phase, 'status': rows[phase].status if phase in rows else 'OPEN'} for phase in ['PRETEST', 'POSTTEST']]}


@study_bp.post('/research/phases/<phase>/close')
@roles_required('RESEARCHER')
def close_phase(phase):
    row = open_phase(phase); payload = data()
    reason = required(payload.get('reason'), 'motivo del cierre', 5, 1000)
    count = db.session.query(Observation).filter_by(phase=phase).count()
    total = db.session.query(ResearchSample).count()
    if count < total and payload.get('confirmIncomplete') is not True:
        return jsonify(message=f'Hay {total-count} equipos sin medición. Confirme el cierre incompleto con su motivo.'), 409
    freeze_census(); row.status = 'CLOSED'; row.reason = reason
    row.closed_by = current_user().id; row.closed_at = datetime.now(timezone.utc)
    audit(current_user().id, 'CLOSE', 'RESEARCH_PHASE', phase, {'reason': reason, 'observed': count, 'target': total})
    db.session.commit(); return {'phase': phase, 'status': 'CLOSED'}


@study_bp.get('/research/evidence/<asset_id>')
@roles_required('RESEARCHER')
def asset_evidence(asset_id):
    if not db.session.get(ResearchSample, asset_id): return jsonify(message='Equipo fuera del censo.'), 404
    checks = db.session.scalars(db.select(InventoryCheck).where(InventoryCheck.asset_id == asset_id).order_by(InventoryCheck.checked_at.desc())).all()
    return [{'result': c.result, 'notes': c.notes, 'checked_at': c.checked_at.isoformat()} for c in checks]


@study_bp.get('/research/audit')
@roles_required('RESEARCHER')
def study_audit():
    rows = db.session.scalars(db.select(AuditLog).where(AuditLog.entity_type.in_(['OBSERVATION', 'REPORT_TRIAL', 'RESEARCH_SAMPLE', 'RESEARCH_PHASE', 'CENSUS']))
                             .order_by(AuditLog.created_at.desc()).limit(500)).all()
    return [{'action': r.action, 'entity': r.entity_type, 'entityId': r.entity_id, 'userId': r.user_id,
             'date': r.created_at.isoformat(), 'details': r.details} for r in rows]


@study_bp.get('/research/dictionary.csv')
@roles_required('RESEARCHER')
def dictionary():
    rows = [['CODIGO_MUESTRA', 'Código estable del equipo en el censo', 'C-0001...', 'Sin SBN'],
            ['ESTRATO', 'Tipo de equipo', 'TYPE_1 / TYPE_2', 'Marco censal'],
            ['PRE_* / POST_*', 'Medición por fase', 'True / False', 'Solo mediciones registradas'],
            ['*_TIEMPO_IDENTIFICACION_MS', 'Tiempo de identificación', 'Milisegundos >= 0', 'No localizado no equivale a tiempo cero'],
            ['DIF_TIEMPO_IDENTIFICACION_MS', 'Postest menos pretest', 'Milisegundos', 'Solo pares completos']]
    return Response(csv_response(['VARIABLE', 'DEFINICION', 'UNIDAD_O_VALORES', 'NOTA'], rows), content_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename=diccionario-estudio.csv'})
