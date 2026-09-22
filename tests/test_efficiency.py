"""Query/session budgets for the refactor, using the isolated regression DB."""
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import test_regressions as isolated  # Sets temporary DB configuration before app imports.
from sqlalchemy import event
from fastapi.testclient import TestClient
from backend.database import engine, SessionLocal
from backend.models import UserTable, TodoTable
from backend.services.reminders import check_deadlines


class EfficiencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with SessionLocal() as db:
            user = UserTable(user_id='efficiency-user', email='efficiency@example.invalid',
                password=isolated.bcrypt.hashpw(b'password123', isolated.bcrypt.gensalt()).decode())
            db.add(user)
            db.commit()
            cls.headers = {'Authorization': 'Bearer ' + isolated.jwt.encode({
                'sub': user.user_id, 'ver': isolated.password_version(user.password),
                'exp': datetime.now() + timedelta(days=1)}, isolated.JWT_SECRET_KEY, algorithm='HS256')}

    def setUp(self):
        self.selects = []
        def record(connection, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith('SELECT'):
                self.selects.append(statement)
        self.record = record
        event.listen(engine, 'before_cursor_execute', record)

    def tearDown(self):
        event.remove(engine, 'before_cursor_execute', self.record)

    def test_create_shares_one_session_and_avoids_reload(self):
        with TestClient(isolated.app) as client, patch('backend.dependencies.SessionLocal', wraps=SessionLocal) as sessions:
            response = client.post('/todos', headers=self.headers, json={'content': 'query budget'})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(sessions.call_count, 1)
            self.assertEqual(len(self.selects), 1)  # Authentication only; INSERT supplies todo defaults.

    def test_subtask_update_uses_two_selects(self):
        with TestClient(isolated.app) as client:
            todo = client.post('/todos', headers=self.headers, json={'content': 'parent'}).json()
            child = client.post(f"/todos/{todo['id']}/subtasks", headers=self.headers, json={'content': 'child'}).json()
            self.selects.clear()
            response = client.patch(f"/subtasks/{child['id']}", headers=self.headers, json={'completed': True})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()['completed'])
            self.assertEqual(len(self.selects), 2)  # Auth plus joined subtask/owner check.

    def test_shared_session_preserves_ownership_checks(self):
        from backend.models import SubtaskTable
        with SessionLocal() as db:
            todo = TodoTable(todo='not owned', owner_id='someone-else')
            db.add(todo)
            db.flush()
            child = SubtaskTable(todo_id=todo.id, content='private child')
            db.add(child)
            db.flush()
            todo_id, child_id = todo.id, child.id
            db.commit()
        with TestClient(isolated.app) as client:
            for method, endpoint, body in [
                ('PATCH', f'/todos/{todo_id}', {'detail': 'changed'}),
                ('PATCH', f'/todos/{todo_id}/toggle', None),
                ('PATCH', f'/subtasks/{child_id}', {'completed': True}),
                ('DELETE', f'/subtasks/{child_id}', None),
            ]:
                response = client.request(method, endpoint, headers=self.headers, json=body)
                self.assertEqual(response.status_code, 403, response.text)
            own = client.get('/todos', headers=self.headers).json()
            self.assertNotIn(todo_id, [item['id'] for item in own])

    def test_reminders_fetch_recipients_in_one_query(self):
        now = datetime(2020, 1, 1, tzinfo=isolated.KST)
        with SessionLocal() as db:
            for index in range(5):
                db.add(TodoTable(todo=f'reminder {index}', owner_id='efficiency-user',
                    deadline=now.replace(tzinfo=None) + timedelta(hours=1)))
            db.commit()
        self.selects.clear()
        with patch('backend.services.reminders.datetime') as clock, patch('backend.services.reminders.send_email') as send, patch('builtins.print'):
            clock.now.return_value = now
            check_deadlines()
            self.assertEqual(send.call_count, 5)
            self.assertEqual(len(self.selects), 1)
            check_deadlines()
            self.assertEqual(send.call_count, 5)  # Already-sent reminders remain excluded.

    def test_backup_flushes_are_batched(self):
        flushes = []
        def record(session, context):
            flushes.append(True)
        event.listen(SessionLocal.class_, 'after_flush', record)
        try:
            with TestClient(isolated.app) as client:
                response = client.post('/todos/import', headers=self.headers, json={'items': [
                    {'content': f'item {i}', 'subtasks': [{'content': 'child'}]} for i in range(20)]})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertLessEqual(len(flushes), 2)
        finally:
            event.remove(SessionLocal.class_, 'after_flush', record)


if __name__ == '__main__':
    unittest.main()
