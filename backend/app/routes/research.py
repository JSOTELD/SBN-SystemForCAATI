from flask import Blueprint, Response, jsonify, request
from sqlalchemy import and_, exists, func
from sqlalchemy.orm import aliased

from ..extensions import db
from ..models import Asset, Observation, ReportTrial, ResearchSample, ResearchSettings
from ..security import auth_required, current_user, roles_required
from ..services.audit import audit
from ..services.research import csv_response, select_stratified
from ..validation import ValidationFailure, data, required

research_bp = Blueprint("research", __name__)


@research_bp.post("/observations")
@roles_required("RESEARCHER")
def save_observation():
    payload = data(); asset_id = required(payload.get("assetId"), "assetId"); phase = payload.get("phase")
    if phase not in {"PRETEST", "POSTTEST"}: raise ValidationFailure("Fase no permitida.")
    if not db.session.get(ResearchSample, asset_id): return jsonify(message="El activo no pertenece a la muestra de investigación."), 409
    from .study import open_phase, freeze_census
    open_phase(phase)
    for key in ['recordComplete', 'recordConsistent', 'correctlyIdentified', 'correctlyRegistered', 'recordUpdated']:
        if type(payload.get(key)) is not bool: raise ValidationFailure('Complete todos los criterios de la guía con Sí o No.')
    row = db.session.execute(db.select(Observation).where(Observation.asset_id == asset_id, Observation.phase == phase)).scalar_one_or_none()
    before = None
    if row:
        if payload.get('version') != row.version: return jsonify(message='La medición cambió. Recargue antes de corregir.'), 409
        required(payload.get('correctionReason'), 'motivo de corrección', 5, 1000)
        before = {'complete': row.record_complete, 'consistent': row.record_consistent, 'identified': row.correctly_identified,
                  'registered': row.correctly_registered, 'updated': row.record_updated, 'durationMs': row.identification_duration_ms,
                  'method': row.identification_method, 'notes': row.notes}
    if not row: row = Observation(asset_id=asset_id, phase=phase, observed_by=current_user().id); db.session.add(row)
    duration = payload.get("identificationDurationMs")
    if type(duration) is not int or duration < 0: raise ValidationFailure("El tiempo de identificación debe ser un entero no negativo.")
    row.record_complete = bool(payload.get("recordComplete")); row.record_consistent = bool(payload.get("recordConsistent"))
    row.correctly_identified = bool(payload.get("correctlyIdentified")); row.identification_method = required(payload.get("identificationMethod"), "identificationMethod", 2, 100)
    row.identification_duration_ms = duration; row.correctly_registered = bool(payload.get("correctlyRegistered")); row.record_updated = bool(payload.get("recordUpdated"))
    row.notes = required(payload['notes'], 'notas', 1, 1000) if payload.get('notes') else None; row.observed_by = current_user().id
    from datetime import datetime, timezone
    row.observed_at = datetime.now(timezone.utc)
    freeze_census()
    audit(current_user().id, "UPSERT", "OBSERVATION", asset_id, {"phase": phase, 'before': before, 'correctionReason': payload.get('correctionReason')}); db.session.commit(); return {"id": row.id, "phase": phase, "assetId": asset_id}, 201


@research_bp.get("/observations")
@auth_required
def observations():
    phase = request.args.get("phase"); query = db.select(Observation)
    if phase: query = query.where(Observation.phase == phase)
    if request.args.get('assetId'): query = query.where(Observation.asset_id == request.args['assetId'])
    rows = db.session.scalars(query.order_by(Observation.observed_at.desc())).all()
    return [{"id": r.id, "phase": r.phase, "asset_id": r.asset_id, "record_complete": r.record_complete,
             "record_consistent": r.record_consistent, "correctly_identified": r.correctly_identified,
             "identification_method": r.identification_method, "identification_duration_ms": r.identification_duration_ms,
             "correctly_registered": r.correctly_registered, "record_updated": r.record_updated, "notes": r.notes, 'version': r.version, 'observed_at': r.observed_at.isoformat()} for r in rows]


@research_bp.post("/report-measurements")
@roles_required("RESEARCHER")
def report_measurement():
    payload = data(); phase = payload.get("phase"); duration = payload.get("durationMs"); code = required(payload.get("measurementCode"), "measurementCode", 3, 50).upper()
    if phase not in {"PRETEST", "POSTTEST"} or not isinstance(duration, int) or duration < 0: raise ValidationFailure("Fase o duración no válida.")
    from .study import open_phase
    open_phase(phase)
    row = db.session.execute(db.select(ReportTrial).where(ReportTrial.measurement_code == code, ReportTrial.phase == phase)).scalar_one_or_none()
    if row: return jsonify(message='La medición de reporte ya existe; se conserva para evitar sobrescrituras.'), 409
    if not row: row = ReportTrial(measurement_code=code, phase=phase, measured_by=current_user().id); db.session.add(row)
    row.report_type = required(payload.get("reportType"), "reportType", 2, 100); row.duration_ms = duration; row.measured_by = current_user().id
    audit(current_user().id, "UPSERT", "REPORT_TRIAL", code, {"phase": phase, "durationMs": duration}); db.session.commit()
    return {"id": row.id, "phase": phase, "measurementCode": code, "reportType": row.report_type, "durationMs": duration}, 201


@research_bp.get("/indicators")
@auth_required
def indicators():
    phase = request.args.get("phase", "POSTTEST"); counterpart = "POSTTEST" if phase == "PRETEST" else "PRETEST"
    counterpart_observation = aliased(Observation)
    paired = exists().where(and_(counterpart_observation.asset_id == Observation.asset_id, counterpart_observation.phase == counterpart))
    rows = db.session.scalars(db.select(Observation).join(ResearchSample, ResearchSample.asset_id == Observation.asset_id).where(Observation.phase == phase, paired)).all()
    codes = set(db.session.scalars(db.select(ReportTrial.measurement_code).where(ReportTrial.phase == counterpart)).all())
    trials = db.session.scalars(db.select(ReportTrial).where(ReportTrial.phase == phase, ReportTrial.measurement_code.in_(codes))).all() if codes else []
    total = len(rows); percent = lambda n: round(n * 100 / total, 2) if total else 0
    observed_phase = db.session.scalar(
        db.select(func.count()).select_from(Observation)
        .join(ResearchSample, ResearchSample.asset_id == Observation.asset_id)
        .where(Observation.phase == phase)
    ) or 0
    selected = db.session.scalar(db.select(func.count(ResearchSample.asset_id))) or 0; settings = db.session.get(ResearchSettings, 1) or ResearchSettings()
    return {"phase": phase, "sampleSize": total, "selectedSize": selected, "targetSize": settings.target_size, "populationSize": settings.population_size,
            "observedInPhase": observed_phase, "excludedUnpaired": max(0, observed_phase-total), "pairedReportTrials": len(trials),
            "PRCC": {"value": percent(sum(r.record_complete and r.record_consistent for r in rows)), "unit": "%", "denominator": total},
            "TPGR": {"value": round(sum(r.duration_ms for r in trials)/len(trials)/1000, 2) if trials else 0, "unit": "s", "measurements": len(trials)},
            "PACI": {"value": percent(sum(r.correctly_identified for r in rows)), "unit": "%", "denominator": total},
            "TPI": {"value": round(sum(r.identification_duration_ms for r in rows)/total/1000, 2) if total else 0, "unit": "s", "measurements": total},
            "PACR": {"value": percent(sum(r.correctly_registered for r in rows)), "unit": "%", "denominator": total},
            "PRA": {"value": percent(sum(r.record_updated for r in rows)), "unit": "%", "denominator": total}}


@research_bp.get("/research/sample")
@auth_required
def sample():
    settings = db.session.get(ResearchSettings, 1) or ResearchSettings(); rows = db.session.execute(db.select(ResearchSample, Asset).join(Asset)).all()
    from ..models import CensusSnapshot
    snapshots = {r.asset_id: r.data for r in db.session.scalars(db.select(CensusSnapshot)).all()}
    phases = {(a, p) for a, p in db.session.execute(db.select(Observation.asset_id, Observation.phase)).all()}
    items = [{"sample_code": s.sample_code, "stratum": s.stratum, "selected_at": s.selected_at.isoformat(), "asset_id": a.id,
              "sbn": snapshots.get(a.id, {}).get('sbn', a.sbn), "description": snapshots.get(a.id, {}).get('description', a.description), "executing_unit": snapshots.get(a.id, {}).get('executingUnit', a.executing_unit), "site": snapshots.get(a.id, {}).get('site', a.site),
              "has_pretest": (a.id, "PRETEST") in phases, "has_posttest": (a.id, "POSTTEST") in phases} for s, a in rows]
    pre = sum(x["has_pretest"] for x in items); post = sum(x["has_posttest"] for x in items); paired = sum(x["has_pretest"] and x["has_posttest"] for x in items)
    counts = {}; [counts.update({x["stratum"]: counts.get(x["stratum"], 0)+1}) for x in items]
    census = settings.selection_seed == 'CENSO_LIBROS_COMERCIO'
    from ..services.census import SITES
    return {"settings": {"sites": SITES if census else [], "selectionMethod": 'CENSUS' if census else 'SAMPLE', "targetSize": settings.target_size, "populationSize": settings.population_size, "selectionSeed": None if census else settings.selection_seed,
             "siteFilter": settings.site_filter, "executingUnits": settings.executing_units, "assetTypes": settings.asset_types},
            "summary": {"selected": len(items), "pretestCount": pre, "posttestCount": post, "pairedCount": paired},
            "byStratum": [{"stratum": k, "total": v} for k, v in sorted(counts.items())], "items": sorted(items, key=lambda x: x["sample_code"])}


@research_bp.post("/research/sample/generate")
@roles_required("RESEARCHER")
def generate_sample():
    payload = data(); settings = db.session.get(ResearchSettings, 1)
    from ..models import CensusSnapshot
    if db.session.scalar(db.select(CensusSnapshot.asset_id).limit(1)) or db.session.scalar(db.select(Observation.id).limit(1)):
        return jsonify(message='El marco está congelado y conserva sus mediciones.'), 409
    if settings and settings.selection_seed == 'CENSO_LIBROS_COMERCIO':
        return jsonify(message='El estudio está configurado como censo de Libros y El Comercio; no corresponde generar una muestra aleatoria.'), 409
    try:
        target = int(payload.get('targetSize', settings.target_size if settings else 361))
    except (TypeError, ValueError):
        raise ValidationFailure('El tamaño de muestra debe ser un entero positivo.')
    seed = required(payload.get("seed", "TESIS-2026"), "seed", 3, 100)
    existing = db.session.scalar(db.select(func.count(ResearchSample.asset_id))) or 0
    if existing and not payload.get("confirmReplace", False): return jsonify(message="Ya existe una muestra. Confirme el reemplazo para volver a seleccionarla; las observaciones históricas no se eliminarán."), 409
    site_filter = str(payload.get("siteFilter", (settings.site_filter or '') if settings else '')).strip(); units = payload.get("executingUnits", ["024", "026", "116"]); types = payload.get("assetTypes", ["TYPE_1", "TYPE_2", "TYPE_3", "PRINTER"])
    normalize = lambda value: str(int("".join(filter(str.isdigit, str(value))) or "0"))
    candidates = [a for a in db.session.scalars(db.select(Asset).where(Asset.status != "BAJA", Asset.asset_type.in_(types))).all()
                  if (not site_filter or site_filter.upper() in a.site.upper()) and normalize(a.executing_unit) in {normalize(x) for x in units}]
    try: selected = select_stratified(candidates, target, seed)
    except ValueError as error: return jsonify(message=str(error)), 409
    db.session.query(ResearchSample).delete()
    for index, asset in enumerate(selected, 1): db.session.add(ResearchSample(asset_id=asset.id, sample_code=f"M-{index:03d}", stratum=asset.asset_type, selected_by=current_user().id))
    settings = db.session.get(ResearchSettings, 1) or ResearchSettings(id=1); db.session.add(settings)
    settings.target_size=target; settings.population_size=len(candidates); settings.selection_seed=seed; settings.site_filter=site_filter or None; settings.executing_units=units; settings.asset_types=types; settings.updated_by=current_user().id
    audit(current_user().id, "REPLACE", "RESEARCH_SAMPLE", details={"selected": len(selected), "seed": seed}); db.session.commit()
    return {"message": f"Muestra estratificada generada con {len(selected)} activos.", "selected": len(selected)}, 201


@research_bp.get("/research/paired-data.csv")
@auth_required
def paired_csv():
    # Explicit query avoids exposing SBN.
    pre = aliased(Observation); post = aliased(Observation)
    pairs = db.session.execute(db.select(ResearchSample, pre, post).join(pre, and_(pre.asset_id==ResearchSample.asset_id, pre.phase=="PRETEST")).join(post, and_(post.asset_id==ResearchSample.asset_id, post.phase=="POSTTEST"))).all()
    rows = [[s.sample_code,s.stratum,a.record_complete,a.record_consistent,a.correctly_identified,a.identification_method,a.identification_duration_ms,a.correctly_registered,a.record_updated,b.record_complete,b.record_consistent,b.correctly_identified,b.identification_method,b.identification_duration_ms,b.correctly_registered,b.record_updated,b.identification_duration_ms-a.identification_duration_ms] for s,a,b in pairs]
    headers=["CODIGO_MUESTRA","ESTRATO","PRE_COMPLETO","PRE_CONSISTENTE","PRE_IDENTIFICADO","PRE_METODO","PRE_TIEMPO_IDENTIFICACION_MS","PRE_REGISTRADO","PRE_ACTUALIZADO","POST_COMPLETO","POST_CONSISTENTE","POST_IDENTIFICADO","POST_METODO","POST_TIEMPO_IDENTIFICACION_MS","POST_REGISTRADO","POST_ACTUALIZADO","DIF_TIEMPO_IDENTIFICACION_MS"]
    return Response(csv_response(headers, rows), content_type="text/csv; charset=utf-8", headers={"Content-Disposition":"attachment; filename=datos-pareados-tesis.csv"})


@research_bp.get("/research/report-trials.csv")
@auth_required
def report_csv():
    pre=aliased(ReportTrial); post=aliased(ReportTrial); pairs=db.session.execute(db.select(pre,post).join(post,and_(post.measurement_code==pre.measurement_code,post.phase=="POSTTEST")).where(pre.phase=="PRETEST")).all()
    rows=[[a.measurement_code,a.report_type,a.duration_ms,b.duration_ms,b.duration_ms-a.duration_ms] for a,b in pairs]
    return Response(csv_response(["CODIGO_MEDICION","TIPO_REPORTE","PRE_TIEMPO_MS","POST_TIEMPO_MS","DIF_TIEMPO_MS"],rows),content_type="text/csv; charset=utf-8",headers={"Content-Disposition":"attachment; filename=tiempos-reportes-pareados.csv"})
