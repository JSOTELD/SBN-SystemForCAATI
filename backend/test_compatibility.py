"""Pruebas aisladas: agrupación y reproducibilidad sin tocar MySQL."""
import unittest
from types import SimpleNamespace
from flask_jwt_extended import create_access_token
from werkzeug.security import generate_password_hash
from app import create_app
from app.extensions import db
from app.models import User, Asset, AssetGroup
from app.services.research import select_stratified


class CompatibilityTest(unittest.TestCase):
    def test_stable_sampling(self):
        first = [SimpleNamespace(id=f'old-{i}', sbn=f'{i:012d}', asset_type='TYPE_1') for i in range(30)]
        second = [SimpleNamespace(id=f'new-{100-i}', sbn=a.sbn, asset_type=a.asset_type) for i, a in enumerate(reversed(first))]
        self.assertEqual([a.sbn for a in select_stratified(first, 8, 'seed')],
                         [a.sbn for a in select_stratified(second, 8, 'seed')])

    def test_imported_components(self):
        app = create_app('testing')
        with app.app_context():
            db.create_all()
            user = User(username='test', email='test@example.test', full_name='Test', role='ADMIN', active=True,
                        password_hash=generate_password_hash('test'), must_change_password=False)
            db.session.add(user)
            groups = [AssetGroup(code=f'GROUP-{kind}', name='Test group', group_type=kind, site='Test')
                      for kind in ['ALL_IN_ONE', 'TYPE_2', 'TYPE_3']]
            db.session.add_all(groups)
            for i, kind in enumerate(['TYPE_1', 'TYPE_2', 'TYPE_3']):
                db.session.add(Asset(sbn=f'74089950A00{i}', asset_type=kind, description='Test asset', site='Test'))
            db.session.commit()
            headers = {'Authorization': 'Bearer ' + create_access_token(identity=user.id, additional_claims={'sv': user.session_version})}
            client = app.test_client()
            bad = client.post(f'/api/asset-groups/{groups[1].id}/members', json={'sbn': '74089950A002', 'componentRole': 'CPU'}, headers=headers)
            self.assertEqual(bad.status_code, 400)
            for i, group in enumerate(groups):
                response = client.post(f'/api/asset-groups/{group.id}/members',
                                       json={'sbn': f'74089950A00{i}', 'componentRole': 'INTEGRATED_UNIT' if i == 0 else 'CPU'}, headers=headers)
                self.assertEqual(response.status_code, 201, response.json)
                self.assertFalse(response.json['complete'])
            again = client.post(f'/api/asset-groups/{groups[0].id}/members', json={'sbn': '74089950A000', 'componentRole': 'INTEGRATED_UNIT'}, headers=headers)
            self.assertEqual(again.status_code, 409)
            db.session.remove()
            db.drop_all()


if __name__ == '__main__':
    unittest.main()
