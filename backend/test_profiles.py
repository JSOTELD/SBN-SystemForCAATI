"""Pruebas integrales en SQLite aislado: no tocan la base patrimonial real."""
import io
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from werkzeug.security import generate_password_hash
from app import create_app
from app.extensions import db
from app.models import (User, Asset, ResearchSample, ResearchSettings, InventorySession,
                        InventoryAssignment, Observation, CensusSnapshot, ResearchPhase)


class ProfilesTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing'); self.context = self.app.app_context(); self.context.push()
        self.temp = tempfile.TemporaryDirectory(); self.app.config['UPLOAD_FOLDER'] = self.temp.name
        db.create_all()
        self.ids = {}
        for name, role in [('admin','ADMIN'),('general','INVENTORY'),('other','INVENTORY'),('research','RESEARCHER')]:
            user=User(username=name,email=name+'@test.local',full_name=name,role=role,password_hash=generate_password_hash('Testing12345!'),must_change_password=False)
            db.session.add(user);db.session.flush();self.ids[name]=user.id
        self.assets=[]
        for index,site in enumerate(['Libros','Comercio','Otra sede']):
            asset=Asset(sbn=f'74089950A00{index}',asset_type='TYPE_1',description='Equipo de prueba',site=site)
            db.session.add(asset);self.assets.append(asset)
        db.session.flush()
        for index,asset in enumerate(self.assets[:2]):db.session.add(ResearchSample(asset_id=asset.id,sample_code=f'C-{index+1:04d}',stratum='TYPE_1',selected_by=self.ids['research']))
        db.session.add(ResearchSettings(id=1,target_size=2,population_size=2,selection_seed='CENSO_LIBROS_COMERCIO'))
        session=InventorySession(name='Prueba asignada',site='Libros',phase='OPERATIVO',created_by=self.ids['admin'])
        db.session.add(session);db.session.flush();self.session_id=session.id
        db.session.add(InventoryAssignment(session_id=session.id,user_id=self.ids['general']))
        db.session.commit()

    def tearDown(self):
        db.session.remove();db.drop_all();self.context.pop();self.temp.cleanup()

    def client(self,name):
        client=self.app.test_client();r=client.post('/api/auth/login',json={'username':name,'password':'Testing12345!'})
        self.assertEqual(r.status_code,200,r.json);self.assertNotIn('token',r.json)
        self.assertTrue(any('HttpOnly' in header for header in r.headers.getlist('Set-Cookie')))
        return client

    def post(self,client,path,payload):
        return client.post(path,json=payload,headers={'X-CSRF-TOKEN':client.get_cookie('csrf_access_token').value})

    def test_role_separation_and_scope(self):
        for name in ['admin','general']:
            c=self.client(name)
            for path in ['/api/research/sample','/api/observations','/api/indicators','/api/research/paired-data.csv','/api/research/phases','/api/research/audit']:
                self.assertEqual(c.get(path).status_code,403,(name,path))
            self.assertEqual(self.post(c,'/api/observations',{}).status_code,403)
        c=self.client('general')
        self.assertEqual(c.get('/api/users').status_code,403)
        self.assertEqual(c.get('/api/audit-logs').status_code,403)
        self.assertEqual(c.get('/api/assets').json['total'],1)
        self.assertEqual(c.get('/api/assets/'+self.assets[2].id).status_code,403)
        self.assertEqual(self.post(c,'/api/assets',{}).status_code,403)
        other=self.client('other')
        self.assertEqual(other.get('/api/inventory-sessions/'+self.session_id).status_code,403)
        researcher=self.client('research')
        self.assertEqual(researcher.get('/api/research/sample').status_code,200)
        self.assertEqual(researcher.get('/api/assets').json['total'],2)
        self.assertEqual(researcher.get('/api/users').status_code,403)
        admin=self.client('admin')
        self.assertFalse(any(u['role']=='RESEARCHER' for u in admin.get('/api/users').json))
        self.assertEqual(self.post(admin,'/api/users/'+self.ids['research']+'/reset-password',{'temporaryPassword':'OtherPass123!'}).status_code,403)

    def test_csrf_and_revocation(self):
        c=self.client('admin')
        self.assertEqual(c.post('/api/auth/logout').status_code,401)
        second=self.client('admin');self.assertEqual(self.post(c,'/api/auth/logout',{}).status_code,200)
        self.assertEqual(second.get('/api/auth/me').status_code,401)

    def test_inventory_conflict_and_photo(self):
        c=self.client('general');path='/api/inventory-sessions/'+self.session_id+'/checks'
        payload={'sbn':self.assets[0].sbn,'result':'MATCH','version':0}
        saved=self.post(c,path,payload);self.assertEqual(saved.status_code,201,saved.json)
        self.assertEqual(self.post(c,path,payload).status_code,409)
        payload.update(version=saved.json['version'],result='MISMATCH',notes='Ubicación diferente',correctionReason='Revisión del usuario')
        corrected=self.post(c,path,payload);self.assertEqual(corrected.status_code,201,corrected.json)
        self.assertEqual(corrected.json['version'],2)
        bad=self.post(c,path,{'sbn':self.assets[1].sbn,'result':'MATCH'});self.assertEqual(bad.status_code,409)
        raw=io.BytesIO();Image.new('RGB',(50,50)).save(raw,format='PNG');raw.seek(0)
        upload=c.post('/api/inventory-checks/'+saved.json['id']+'/evidence',data={'photo':(raw,'test.png')},headers={'X-CSRF-TOKEN':c.get_cookie('csrf_access_token').value})
        self.assertEqual(upload.status_code,201,upload.json)
        url='/api/inventory-evidence/'+upload.json['id']
        response=c.get(url);self.assertEqual(response.status_code,200);response.close()
        self.assertEqual(self.client('other').get(url).status_code,403)
        admin=self.client('admin');self.assertEqual(self.post(admin,'/api/inventory-sessions/'+self.session_id+'/close',{}).status_code,200)
        self.assertEqual(self.post(c,path,payload).status_code,409)

    def test_research_freeze_corrections_and_close(self):
        c=self.client('research');a=self.assets[0]
        p={'assetId':a.id,'phase':'PRETEST','recordComplete':True,'recordConsistent':True,'correctlyIdentified':True,
           'correctlyRegistered':False,'recordUpdated':False,'identificationMethod':'Manual','identificationDurationMs':5000}
        r=self.post(c,'/api/observations',p);self.assertEqual(r.status_code,201,r.json)
        self.assertEqual(db.session.query(CensusSnapshot).count(),2)
        self.assertEqual(self.post(c,'/api/observations',p).status_code,409)
        old=c.get('/api/observations').json[0]
        p.update(version=old['version'],correctionReason='Corregir duración',identificationDurationMs=6000)
        self.assertEqual(self.post(c,'/api/observations',p).status_code,201)
        a.site='Nueva ubicación';db.session.commit()
        row=next(x for x in c.get('/api/research/sample').json['items'] if x['asset_id']==a.id)
        self.assertEqual(row['site'],'Libros')
        closed=self.post(c,'/api/research/phases/PRETEST/close',{'reason':'Cierre de prueba','confirmIncomplete':True})
        self.assertEqual(closed.status_code,200,closed.json)
        self.assertEqual(self.post(c,'/api/observations',p).status_code,400)
        self.assertEqual(self.client('admin').get('/api/research/audit').status_code,403)
        self.assertNotIn(a.sbn,c.get('/api/research/paired-data.csv').get_data(as_text=True))


if __name__=='__main__':unittest.main(verbosity=2)
