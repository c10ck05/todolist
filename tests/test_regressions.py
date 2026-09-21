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
from backend.models import UserTable, EmailVerificationTable, AuthRateLimitTable, SubtaskTable, TodoTable
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
            db.add(EmailVerificationTable(email='security@example.invalid', purpose='reset', code='123456',
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

    def test_new_password_policy_on_all_three_endpoints(self):
        with TestClient(app) as client:
            headers = self.login(client)
            for password in ['', '1234567', '        ', '가' * 25, 'a' * 73, None, 12345678]:
                for path, body in [
                    ('/signup', {'username': 'new-user', 'email': 'new@example.invalid',
                                 'code': '123456', 'password': password}),
                    ('/reset-password', {'email': 'security@example.invalid',
                                         'code': '123456', 'new_password': password}),
                    ('/change-password', {'current_password': 'password123', 'new_password': password}),
                ]:
                    with self.subTest(path=path, password_type=type(password).__name__):
                        response = client.post(path, headers=headers, json=body)
                        self.assertEqual(response.status_code, 422, response.text)
                        self.assertIsInstance(response.json()['detail'], str)
            # 24 Korean characters = exactly 72 UTF-8 bytes.
            self.assertEqual(client.post('/change-password', headers=headers, json={
                'current_password': 'password123', 'new_password': '가' * 24}).status_code, 200)
            self.login(client, '가' * 24)

    def test_legacy_short_password_still_logs_in(self):
        with SessionLocal() as db:
            user = db.query(UserTable).filter_by(user_id='security-user').one()
            user.password = bcrypt.hashpw(b'1234', bcrypt.gensalt()).decode()
            db.commit()
        with TestClient(app) as client:
            self.login(client, '1234')

    def test_verification_purposes_and_single_use(self):
        with SessionLocal() as db:
            db.query(EmailVerificationTable).delete()
            db.commit()
        with TestClient(app) as client, patch('backend.routers.auth.send_email'):
            self.assertEqual(client.post('/request-code', json={
                'email': 'security@example.invalid'}).status_code, 200)
            with SessionLocal() as db:
                code = db.get(EmailVerificationTable, ('security@example.invalid', 'signup')).code
            self.assertEqual(client.post('/reset-password', json={
                'email': 'security@example.invalid', 'code': code,
                'new_password': 'password456'}).status_code, 400)
            # Reset-only code cannot create an account, even with the correct digits.
            with SessionLocal() as db:
                db.add(EmailVerificationTable(email='new@example.invalid', purpose='reset', code='654321',
                       expires_at=datetime.now(KST).replace(tzinfo=None) + timedelta(minutes=3)))
                db.commit()
            signup = {'username': 'new-user', 'email': 'new@example.invalid',
                      'password': 'password123', 'code': '654321'}
            self.assertEqual(client.post('/signup', json=signup).status_code, 400)
            self.assertEqual(client.post('/request-code', json={'email': signup['email']}).status_code, 200)
            with SessionLocal() as db:
                signup['code'] = db.get(EmailVerificationTable, (signup['email'], 'signup')).code
            self.assertEqual(client.post('/signup', json=signup).status_code, 200)
            self.assertEqual(client.post('/signup', json=signup).status_code, 400)

    def test_malformed_requests_are_client_errors(self):
        with TestClient(app, raise_server_exceptions=False) as client:
            headers = self.login(client)
            todo = client.post('/todos', headers=headers, json={'content': 'validation'}).json()
            sub = client.post(f"/todos/{todo['id']}/subtasks", headers=headers,
                              json={'content': 'child'}).json()
            cases = [
                ('POST', '/login', {'username': 'security-user'}),
                ('POST', '/login', {'username': 'security-user', 'password': 'a' * 73}),
                ('POST', '/todos', {}),
                ('POST', '/todos', {'content': '  '}),
                ('POST', '/todos', {'content': 123}),
                ('POST', '/todos', {'content': 'test', 'deadline': 'not-a-date'}),
                ('POST', '/todos', {'content': 'test', 'deadline': 123}),
                ('POST', '/todos', {'content': 'test', 'priority': True}),
                ('PATCH', f"/todos/{todo['id']}", {'content': None}),
                ('PATCH', f"/todos/{todo['id']}", {'priority': None}),
                ('PATCH', f"/todos/{todo['id']}", {'category': []}),
                ('PATCH', f"/todos/{todo['id']}/deadline", {}),
                ('PATCH', f"/todos/{todo['id']}/deadline", {'deadline': 'bad-date'}),
                ('POST', '/todos/reorder', {'order': [{}]}),
                ('POST', '/todos/reorder', {'order': [todo['id'], todo['id']]}),
                ('POST', f"/todos/{todo['id']}/subtasks", {'content': None}),
                ('PATCH', f"/subtasks/{sub['id']}", {'completed': 'false'}),
                ('PATCH', f"/subtasks/{sub['id']}", {'completed': None}),
                ('DELETE', '/account', {'password': 123}),
            ]
            for method, path, body in cases:
                with self.subTest(method=method, path=path, body=body):
                    response = client.request(method, path, headers=headers, json=body)
                    self.assertEqual(response.status_code, 422, response.text)
            response = client.patch(f"/todos/{todo['id']}/deadline", headers=headers,
                                    json={'deadline': '2026-09-22T00:00:00Z'})
            self.assertEqual(response.json()['deadline'], '2026-09-22T09:00:00')
            self.assertEqual(client.patch(f"/todos/{todo['id']}/deadline", headers=headers,
                                         json={'deadline': None}).status_code, 200)

    def test_delete_removes_only_owned_checklist(self):
        with TestClient(app) as client:
            headers = self.login(client)
            ids = []
            for _ in range(2):
                todo = client.post('/todos', headers=headers, json={'content': 'delete test'}).json()
                ids.append(todo['id'])
                client.post(f"/todos/{todo['id']}/subtasks", headers=headers, json={'content': 'child'})
            self.assertEqual(client.delete(f'/todos/{ids[0]}', headers=headers).status_code, 200)
            with SessionLocal() as db:
                self.assertEqual(db.query(SubtaskTable).filter_by(todo_id=ids[0]).count(), 0)
                self.assertEqual(db.query(SubtaskTable).filter_by(todo_id=ids[1]).count(), 1)

    def test_password_rechecks_share_a_persistent_limit(self):
        with TestClient(app) as client:
            headers = self.login(client)
            for index in range(10):
                if index % 2:
                    response = client.request('DELETE', '/account', headers=headers, json={'password': 'wrong'})
                else:
                    response = client.post('/change-password', headers=headers, json={
                        'current_password': 'wrong', 'new_password': 'password456'})
                self.assertEqual(response.status_code, 400)
            with patch('backend.routers.account.bcrypt.checkpw') as check:
                for method, path, data in [
                    ('POST', '/change-password', {'current_password': 'password123', 'new_password': 'password456'}),
                    ('DELETE', '/account', {'password': 'password123'}),
                ]:
                    response = client.request(method, path, headers=headers, json=data)
                    self.assertEqual(response.status_code, 429)
                    self.assertIn('retry-after', response.headers)
                check.assert_not_called()
            self.assertEqual(client.get('/todos', headers=headers).status_code, 200)

    def test_repeat_bounds_and_date_overflow(self):
        with TestClient(app, raise_server_exceptions=False) as client:
            headers = self.login(client)
            for repeat, deadline in [
                ({'type': 'interval', 'value': 1000000000}, '2026-09-22T12:00'),
                ({'type': 'interval', 'value': 3651}, '2026-09-22T12:00'),
                ({'type': 'daily'}, '9999-12-31T12:00'),
                ({'type': 'weekly', 'days': ['mon']}, '9999-12-31T12:00'),
                ({'type': 'monthly'}, '9999-12-31T12:00'),
            ]:
                response = client.post('/todos', headers=headers, json={
                    'content': 'invalid repeat', 'repeat': repeat, 'deadline': deadline})
                self.assertEqual(response.status_code, 400, response.text)
            created = client.post('/todos', headers=headers, json={'content': 'valid repeat',
                'deadline': '2026-09-22T12:00', 'repeat': {'type': 'interval', 'value': 3650}})
            self.assertEqual(created.status_code, 200)
            todo_id = created.json()['id']
            self.assertEqual(client.patch(f'/todos/{todo_id}/deadline', headers=headers,
                json={'deadline': '9999-12-31T12:00'}).status_code, 400)
            # Old invalid rows should fail gracefully and still be repairable.
            with SessionLocal() as db:
                db.get(TodoTable, todo_id).repeat_cycle = {'type': 'interval', 'value': 1000000000}
                db.commit()
            self.assertEqual(client.patch(f'/todos/{todo_id}/toggle', headers=headers).status_code, 400)
            with SessionLocal() as db:
                self.assertFalse(db.get(TodoTable, todo_id).completed)
            self.assertEqual(client.patch(f'/todos/{todo_id}', headers=headers,
                json={'repeat': {'type': 'daily'}}).status_code, 200)
            self.assertEqual(client.patch(f'/todos/{todo_id}/toggle', headers=headers).status_code, 200)

    def test_backup_roundtrip_and_atomic_rollback(self):
        from sqlalchemy import event
        with TestClient(app, raise_server_exceptions=False) as client:
            headers = self.login(client)
            backup = [{'id': 987654, 'content': 'restored', 'completed': True,
                       'deadline': '2026-09-22T12:00:00', 'category': 'home',
                       'repeat': {'type': 'weekly', 'days': ['mon', 'wed', 'fri']},
                       'priority': 2, 'detail': 'memo', 'sort_order': 3,
                       'subtasks': [{'id': 987655, 'content': 'child', 'completed': True}]},
                      {'content': 'first', 'completed': False, 'sort_order': 1}]
            before = client.get('/todos', headers=headers).json()
            response = client.post('/todos/import', headers=headers, json={'items': backup})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['imported'], 2)
            after = client.get('/todos', headers=headers).json()
            self.assertEqual([t['id'] for t in after[:-2]], [t['id'] for t in before])
            self.assertEqual(after[-2]['content'], 'first')
            restored = after[-1]
            for key in ['content', 'completed', 'deadline', 'category', 'repeat', 'priority', 'detail']:
                self.assertEqual(restored[key], backup[0][key])
            self.assertNotEqual(restored['id'], backup[0]['id'])
            self.assertEqual(restored['subtasks'][0]['content'], 'child')
            self.assertTrue(restored['subtasks'][0]['completed'])
            # Invalid later entries must not leave a partially restored backup.
            self.assertEqual(client.post('/todos/import', headers=headers,
                json={'items': [backup[0], {'content': None}]}).status_code, 422)
            self.assertEqual(client.get('/todos', headers=headers).json(), after)
            def fail_insert(*args):
                raise RuntimeError('simulated child insert failure')
            event.listen(SubtaskTable, 'before_insert', fail_insert)
            try:
                self.assertEqual(client.post('/todos/import', headers=headers,
                    json={'items': backup}).status_code, 500)
            finally:
                event.remove(SubtaskTable, 'before_insert', fail_insert)
            self.assertEqual(client.get('/todos', headers=headers).json(), after)


if __name__ == '__main__':
    unittest.main()
