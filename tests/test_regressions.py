"""Isolated regression checks; never connects to the configured production DB."""
import os
import tempfile
import unittest
from datetime import datetime
from datetime import timedelta
from unittest.mock import patch
import bcrypt

_temporary = tempfile.TemporaryDirectory()
os.environ['DATABASE_URL'] = f'sqlite:///{_temporary.name}/test.sqlite'
os.environ['JWT_SECRET_KEY'] = 'test-only-secret-key-at-least-32-characters'

import jwt
from fastapi.testclient import TestClient
from main import app
from backend.config import JWT_SECRET_KEY
from backend.utils.todos import add_interval
from backend.database import SessionLocal
from backend.models import UserTable, EmailVerificationTable, AuthRateLimitTable
from backend.config import KST
from backend.security import password_version


class RegressionTests(unittest.TestCase):
    def test_checklist_and_recompletion(self):
        with SessionLocal() as db:
            user = UserTable(user_id='regression-user', email='regression@example.invalid',
                             password=bcrypt.hashpw(b'password123', bcrypt.gensalt()).decode())
            db.add(user)
            db.commit()
            version = password_version(user.password)
        headers = {'Authorization': 'Bearer ' + jwt.encode(
            {'sub': 'regression-user', 'ver': version, 'exp': datetime.now() + timedelta(days=1)}, JWT_SECRET_KEY, algorithm='HS256')}
        with TestClient(app) as client:
            created = client.post('/todos', headers=headers, json={
                'content': 'test', 'deadline': '2026-09-21T10:00',
                'repeat': {'type': 'weekly', 'days': ['mon', 'wed', 'fri']}})
            self.assertEqual(created.status_code, 200)
            todo_id = created.json()['id']
            sub = client.post(f'/todos/{todo_id}/subtasks', headers=headers,
                              json={'content': 'child'}).json()
            updated = client.patch(f'/todos/{todo_id}', headers=headers,
                                   json={'detail': 'memo'}).json()
            self.assertEqual(updated['subtasks'], [sub])
            for _ in range(3):
                result = client.patch(f'/todos/{todo_id}/toggle', headers=headers)
                self.assertEqual(result.status_code, 200)
            self.assertNotIn('spawned', result.json())
            todos = client.get('/todos', headers=headers).json()
            self.assertEqual(len(todos), 2)
            self.assertEqual(todos[1]['deadline'], '2026-09-23T10:00:00')

    def test_month_boundaries(self):
        for start, expected in [
            ('2026-01-31T10:30', '2026-02-28T10:30'),
            ('2028-01-31T10:30', '2028-02-29T10:30'),
            ('2026-12-15T10:30', '2027-01-15T10:30'),
        ]:
            self.assertEqual(add_interval(datetime.fromisoformat(start), {'type': 'monthly'}),
                             datetime.fromisoformat(expected))


class SecurityTests(unittest.TestCase):
    def setUp(self):
        with SessionLocal() as db:
            db.query(AuthRateLimitTable).delete()
            db.query(EmailVerificationTable).delete()
            db.query(UserTable).filter(UserTable.user_id == 'security-user').delete()
            db.add(UserTable(user_id='security-user', email='security@example.invalid',
                             password=bcrypt.hashpw(b'password123', bcrypt.gensalt()).decode()))
            db.add(EmailVerificationTable(email='security@example.invalid', code='123456',
                    expires_at=datetime.now(KST).replace(tzinfo=None) + timedelta(minutes=3)))
            db.commit()

    def login(self, client, password='password123'):
        response = client.post('/login', json={'username':'security-user', 'password':password})
        self.assertEqual(response.status_code, 200, response.text)
        return {'Authorization': 'Bearer ' + response.json()['access_token']}

    def test_password_change_and_reset_revoke_tokens(self):
        with TestClient(app) as client:
            old = self.login(client)
            self.assertEqual(client.post('/change-password', headers=old, json={
                'current_password':'password123', 'new_password':'password456'}).status_code, 200)
            self.assertEqual(client.get('/todos', headers=old).status_code, 401)
            fresh = self.login(client, 'password456')
            self.assertEqual(client.get('/todos', headers=fresh).status_code, 200)
            self.assertEqual(client.post('/reset-password', json={
                'email':'security@example.invalid', 'code':'123456', 'new_password':'password789'}).status_code, 200)
            self.assertEqual(client.get('/todos', headers=fresh).status_code, 401)
            self.assertEqual(client.get('/todos', headers=self.login(client, 'password789')).status_code, 200)

    def test_code_attempts_and_resend_do_not_reset_limit(self):
        with TestClient(app) as client, patch('backend.routers.auth.send_email') as send:
            body = {'email':'security@example.invalid', 'code':'000000', 'new_password':'password456'}
            for _ in range(5):
                self.assertEqual(client.post('/reset-password', json=body).status_code, 400)
            response = client.post('/reset-password', json={**body, 'code':'123456'})
            self.assertEqual(response.status_code, 429)
            self.assertIn('retry-after', response.headers)
            self.assertEqual(client.post('/request-reset-code', json={'email':body['email']}).status_code, 200)
            self.assertEqual(client.post('/request-code', json={'email':body['email']}).status_code, 429)
            self.assertEqual(send.call_count, 1)
            self.assertEqual(client.post('/reset-password', json=body).status_code, 429)

    def test_login_throttle_and_legacy_token(self):
        with TestClient(app) as client:
            legacy = jwt.encode({'sub':'security-user', 'exp':datetime.now()+timedelta(days=1)},
                                JWT_SECRET_KEY, algorithm='HS256')
            self.assertEqual(client.get('/todos', headers={'Authorization':'Bearer '+legacy}).status_code, 401)
            for _ in range(10):
                self.assertEqual(client.post('/login', json={'username':'security-user','password':'wrong'}).status_code, 401)
            self.assertEqual(client.post('/login', json={'username':'security-user','password':'password123'}).status_code, 429)


if __name__ == '__main__':
    unittest.main()
