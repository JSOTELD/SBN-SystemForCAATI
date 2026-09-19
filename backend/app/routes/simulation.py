import csv
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from flask import Blueprint, Response, abort, jsonify, request, render_template_string
from ..extensions import db
from ..models import SimulationStudy, SimulationAsset, AuditLog
from ..security import roles_required, current_user
from ..services.guide_audit import METRICS, digest, reconcile
from ..services.audit import audit
from ..services.research import csv_response

guide_audit_bp = Blueprint('guide_audit', __name__)


def study_or_404(study_id):
    study = db.session.get(SimulationStudy, study_id)
    if study is None: abort(404)
    return study


def details(study_id):
    return [{'sample_code':a.sample_code,'snapshot':a.snapshot,'pre':a.pre,'post':a.post}
            for a in db.session.scalars(db.select(SimulationAsset).where(SimulationAsset.study_id==study_id).order_by(SimulationAsset.sample_code)).all()]


def verification(study):
    generated = details(study.id)
    checks = reconcile(study.guides,generated)
    hashes = {'source':hashlib.sha256(study.source_blob).hexdigest()==study.source_hash,
              'guides':digest(study.guides)==study.manifest['guidesHash'],
              'details':digest(generated)==study.manifest['detailsHash']}
    codes=[row['sample_code'] for row in generated]
    identity=len(codes)==len(set(codes))==study.manifest['population']
    return {'passed':identity and all(hashes.values()) and all(row['passed'] for row in checks),
            'hashes':hashes,'uniquePopulation':identity,'checks':checks,
            'passedChecks':sum(row['passed'] for row in checks),'totalChecks':len(checks),
            'findings':study.manifest['findings'],
            'meaning':'Comprueba integridad y conciliación aritmética; no valida autenticidad empírica.'}


def overview(study):
    return {'id':study.id,'filename':study.filename,'createdAt':study.created_at.isoformat(),
            'manifest':study.manifest,
            'guides':[{k:v for k,v in study.guides[metric].items() if k!='rows'}|{'metric':metric} for metric in METRICS]}


@guide_audit_bp.get('/research/simulations')
@roles_required('RESEARCHER')
def studies():
    rows=db.session.scalars(db.select(SimulationStudy).order_by(SimulationStudy.created_at.desc())).all()
    return [overview(row) for row in rows]


@guide_audit_bp.get('/research/simulations/<study_id>/guides/<metric>')
@roles_required('RESEARCHER')
def guide(study_id,metric):
    study=study_or_404(study_id)
    if metric not in METRICS: abort(404)
    return study.guides[metric]


@guide_audit_bp.get('/research/simulations/<study_id>/assets')
@roles_required('RESEARCHER')
def assets(study_id):
    study_or_404(study_id)
    query=db.select(SimulationAsset).where(SimulationAsset.study_id==study_id)
    day=request.args.get('day',type=int)
    # El total es pequeño (1693 pares); filtro por JSON portable entre SQLite/MySQL.
    rows=db.session.scalars(query.order_by(SimulationAsset.sample_code)).all()
    if day: rows=[a for a in rows if a.pre['day']==day]
    search=request.args.get('search','').strip().casefold()
    if search: rows=[a for a in rows if search in (a.sample_code+' '+a.snapshot['sbn']+' '+a.snapshot['site']).casefold()]
    page=max(1,request.args.get('page',1,type=int)); size=min(100,max(1,request.args.get('pageSize',30,type=int)))
    return {'items':[{'sample_code':a.sample_code,'snapshot':a.snapshot,'pre':a.pre,'post':a.post} for a in rows[(page-1)*size:page*size]],
            'total':len(rows),'page':page,'pageSize':size,'nature':'DERIVED_DISAGGREGATION'}


@guide_audit_bp.post('/research/simulations/<study_id>/verify')
@roles_required('RESEARCHER')
def verify(study_id):
    report=verification(study_or_404(study_id))
    audit(current_user().id,'VERIFY_GUIDES','SIMULATION_STUDY',study_id,{'passed':report['passed'],'passedChecks':report['passedChecks'],'totalChecks':report['totalChecks']})
    db.session.commit(); return report


@guide_audit_bp.get('/research/simulations/<study_id>/events')
@roles_required('RESEARCHER')
def events(study_id):
    study_or_404(study_id)
    rows=db.session.scalars(db.select(AuditLog).where(AuditLog.entity_type=='SIMULATION_STUDY',AuditLog.entity_id==study_id).order_by(AuditLog.created_at.desc())).all()
    return [{'at':r.created_at.isoformat(),'action':r.action,'userId':r.user_id,'details':r.details} for r in rows]


REPORT = '''<!doctype html><html lang="es"><meta charset="utf-8"><title>Informe de guías</title>
<style>body{font:14px Arial;margin:30px;color:#172a40}h1{font-size:24px}table{border-collapse:collapse;width:100%;margin:14px 0}td,th{border:1px solid #bcc9d8;padding:6px;text-align:right}th:first-child,td:first-child{text-align:left}.notice{border:2px solid #b87413;padding:14px;background:#fff6df}section{break-before:page}thead{display:table-header-group}@media print{body{margin:10mm;font-size:11px}a{color:inherit}}</style>
<h1>Informe de guías — fases pretest y postest</h1><div class="notice"><strong>ALCANCE DEL INFORME.</strong>
Pretest agregado: declarado por el usuario, no verificado con evidencia primaria.
Postest: agregado según la fuente. El archivo identifica ambas fases como sintéticas. El detalle por equipo es derivado de los agregados.</div>
<p>Fuente: {{ study.filename }}<br>SHA-256: {{ study.source_hash }}<br>Versión: {{ study.manifest.algorithm }} · Semilla: {{ study.manifest.seed }}</p>
<p>Población del estudio: {{ study.manifest.population }}. Conciliación: {{ report.passedChecks }}/{{ report.totalChecks }} controles aritméticos correctos.
Integridad: {{ 'CORRECTA' if report.passed else 'REVISAR' }}. Estos controles no certifican resultados empíricos.</p>
<h2>Acotaciones de auditoría</h2><ul>{% for finding in report.findings %}<li><strong>{{ finding.code }}</strong>: {{ finding.message }}</li>{% endfor %}</ul>
{% for metric,guide in study.guides.items() %}<section><h2>{{ metric }} — {{ guide.title }}</h2><p>{{ guide.formula }}<br>{{ guide.definition }}</p>
<p>Pretest: {{ '%.4f'|format(guide.summary.PRETEST.value) }} {{guide.unit}} · Postest: {{ '%.4f'|format(guide.summary.POSTTEST.value) }} {{guide.unit}}.</p>
<table><thead><tr><th>Día</th><th>Fecha pre</th><th>Total pre</th><th>Numerador pre</th><th>Resultado pre</th><th>Fecha post</th><th>Total post</th><th>Numerador post</th><th>Resultado post</th></tr></thead><tbody>
{% for row in guide.rows %}<tr><td>{{row.day}}</td><td>{{row.PRETEST.date}}</td><td>{{row.PRETEST.denominator}}</td><td>{{row.PRETEST.numerator}}</td><td>{{'%.4f'|format(row.PRETEST.value)}}</td><td>{{row.POSTTEST.date}}</td><td>{{row.POSTTEST.denominator}}</td><td>{{row.POSTTEST.numerator}}</td><td>{{'%.4f'|format(row.POSTTEST.value)}}</td></tr>{% endfor %}</tbody></table><p>{{guide.note}}</p></section>{% endfor %}</html>'''


@guide_audit_bp.get('/research/simulations/<study_id>/report')
@roles_required('RESEARCHER')
def report(study_id):
    study=study_or_404(study_id)
    template = REPORT
    notice_start = template.index('<div class="notice">')
    notice_end = template.index('</div>', notice_start) + len('</div>')
    template = template[:notice_start] + template[notice_end:]
    findings_start = template.index('<h2>Acotaciones de auditoría</h2>')
    findings_end = template.index('</ul>', findings_start) + len('</ul>')
    template = template[:findings_start] + '<p>Acotaciones y procedencia disponibles en el expediente técnico.</p>' + template[findings_end:]
    template = template.replace('<p>{{guide.note}}</p>', '')
    return render_template_string(template, study=study, report=verification(study))


@guide_audit_bp.get('/research/simulations/<study_id>/audit.zip')
@roles_required('RESEARCHER')
def export_audit(study_id):
    study=study_or_404(study_id); report=verification(study); generated=details(study_id)
    guide_rows=[]
    for metric in METRICS:
        for pair in study.guides[metric]['rows']:
            for phase in ['PRETEST','POSTTEST']:
                r=pair[phase]
                guide_rows.append([metric,phase,r['nature'],pair['day'],r['date'],r['denominator'],r['numerator'],r['value'],study.guides[metric]['sheet'],r['sourceRange'],r['code'],r['profile']])
    detail_rows=[]
    for a in generated:
        for phase,key in [('PRETEST','pre'),('POSTTEST','post')]:
            r=a[key]
            detail_rows.append([a['sample_code'],a['snapshot']['stratum'],a['snapshot']['site'],phase,r['nature'],r['day'],r['date'],r['PRCC'],r['PACI'],r['PACR'],r['PRA'],r['durationMs']])
    checks=report['checks']
    files={
        'fuente_original.xlsx':study.source_blob,
        'guias_diarias.csv':csv_response(['INDICADOR','FASE','NATURALEZA','DIA','FECHA','DENOMINADOR','NUMERADOR','RESULTADO','HOJA','RANGO','CODIGO_REPORTE','PERFIL'],guide_rows).encode('utf-8'),
        'detalle_por_equipo.csv':csv_response(['CODIGO_CENSO','ESTRATO','SEDE','FASE','NATURALEZA','DIA','FECHA','PRCC_CONJUNTO','PACI','PACR','PRA','TIEMPO_MS'],detail_rows).encode('utf-8'),
        'conciliacion.csv':csv_response(list(checks[0]),[[r[k] for k in checks[0]] for r in checks]).encode('utf-8'),
        'informe_guias.html':render_template_string(REPORT,study=study,report=report).encode('utf-8'),
        'LEER_PRIMERO.txt':('INFORME DE GUÍAS.\nPretest agregado declarado por el usuario; el libro lo rotula sintético. Postest según la fuente.\n'
                   'El detalle individual de ambas fases es una derivación técnica, no evidencia primaria ni base inferencial empírica.\n'
                           'PRCC representa cumple ambos criterios; no identifica cuál falla. Fechas conservadas del archivo, no fechas de carga.\n'
                           'Los controles verifican coherencia aritmética e integridad; no autenticidad. No se modificaron observaciones reales.\n').encode('utf-8')}
    manifest={**study.manifest,'studyId':study.id,'exportedAt':datetime.now(timezone.utc).isoformat(),
              'verification':{k:v for k,v in report.items() if k!='checks'},
              'files':{name:hashlib.sha256(blob).hexdigest() for name,blob in files.items()}}
    files['manifest.json']=json.dumps(manifest,ensure_ascii=False,indent=2).encode('utf-8')
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,blob in files.items(): archive.writestr(name,blob)
    audit(current_user().id,'EXPORT_GUIDES','SIMULATION_STUDY',study_id,{'files':list(files),'passed':report['passed']});db.session.commit()
    return Response(output.getvalue(),mimetype='application/zip',headers={'Content-Disposition':'attachment; filename=expediente_guias_N1693.zip'})
