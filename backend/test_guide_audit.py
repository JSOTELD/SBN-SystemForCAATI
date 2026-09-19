"""Validación aislada de guías, derivación, permisos y expediente."""
import copy
import hashlib
import io
import json
import unittest
import zipfile
from pathlib import Path
from werkzeug.security import generate_password_hash
from app import create_app
from app.extensions import db
from app.models import User, Asset, ResearchSample, Observation, GuideAsset
from app.services.guide_audit import import_guides, derive_details, reconcile
from app.routes.guide_audit import verification, details

SOURCE=Path('C:/Users/USER/Downloads/Guias_30_dias_N1693_DATOS_PRACTICA.xlsx')

class GuideAuditTest(unittest.TestCase):
    def test_import_audit_and_isolation(self):
        app=create_app('testing')
        with app.app_context():
            db.create_all()
            try:
                users={}
                for name,role in [('research','RESEARCHER'),('admin','ADMIN'),('general','INVENTORY')]:
                    u=User(username=name,email=name+'@test.local',full_name=name,role=role,password_hash=generate_password_hash('Testing12345!'),must_change_password=False)
                    db.session.add(u);db.session.flush();users[name]=u.id
                for i in range(1693):
                    a=Asset(sbn=f'{i:012d}',description='Prueba',asset_type='TYPE_1',site='Libros');db.session.add(a);db.session.flush()
                    db.session.add(ResearchSample(asset_id=a.id,sample_code=f'C-{i+1:04d}',stratum='TYPE_1',selected_by=users['research']))
                db.session.commit()
                study,created=import_guides(SOURCE,users['research']);self.assertTrue(created)
                self.assertFalse(import_guides(SOURCE,users['research'])[1])
                report=verification(study);self.assertTrue(report['passed']);self.assertEqual(report['passedChecks'],360)
                generated=details(study.id)
                self.assertEqual(derive_details(study.guides,[{'sample_code':r['sample_code'],'snapshot':r['snapshot']} for r in generated]),generated)
                altered=copy.deepcopy(generated);altered[0]['pre']['durationMs']+=1000
                self.assertFalse(all(c['passed'] for c in reconcile(study.guides,altered)))
                self.assertEqual(db.session.scalar(db.select(db.func.count()).select_from(Observation)),0)
                self.assertEqual(study.guides['PRCC']['summary']['PRETEST']['numerator'],1121)
                self.assertEqual(study.guides['PRCC']['summary']['POSTTEST']['numerator'],1601)
                base='/api/research/guides/'+study.id
                for name in users:
                    c=app.test_client();self.assertEqual(c.post('/api/auth/login',json={'username':name,'password':'Testing12345!'}).status_code,200)
                    for path in ['/api/research/guides',base+'/assets',base+'/report',base+'/audit.zip',base+'/events',base+'/guides/PRCC']:
                        response=c.get(path);self.assertEqual(response.status_code,200 if name=='research' else 403,path)
                        if name=='research' and path.endswith('.zip'):
                            with zipfile.ZipFile(io.BytesIO(response.data)) as z:
                                manifest=json.loads(z.read('manifest.json'))
                                for file,sha in manifest['files'].items():self.assertEqual(hashlib.sha256(z.read(file)).hexdigest(),sha)
                                self.assertEqual(z.read('fuente_original.xlsx'),SOURCE.read_bytes())
                    r=c.post(base+'/verify',json={},headers={'X-CSRF-TOKEN':c.get_cookie('csrf_access_token').value})
                    self.assertEqual(r.status_code,200 if name=='research' else 403)
                row=db.session.scalar(db.select(GuideAsset));row.pre={**row.pre,'durationMs':row.pre['durationMs']+1};db.session.commit()
                self.assertFalse(verification(study)['passed'])
            finally:db.session.remove();db.drop_all()

if __name__=='__main__':unittest.main()
