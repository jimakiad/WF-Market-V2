import os
import sys
import threading
import time
import unittest
from unittest.mock import Mock, patch

import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backend'))
import app as server
import create_orders as creator
import delete_orders as deleter

CATALOGUE = {
    'mods': {'Red Veil': [{'Name': 'Test Augment', 'URL_Name': 'test_augment', 'id': 'mod-1'}]},
    'thumbs': {},
}


class PublicHostingTests(unittest.TestCase):
    def setUp(self):
        server.app.config.update(TESTING=True, SECRET_KEY='test-secret', SESSION_COOKIE_SECURE=False)
        server.operations.clear()
        server.batch_jobs.clear()
        self.alice = self.client('Alice', 'JWT alice')
        self.bob = self.client('Bob', 'JWT bob')
        self.catalogue = patch.object(server, 'get_catalogue', return_value=CATALOGUE)
        self.catalogue.start()
        self.addCleanup(self.catalogue.stop)

    def client(self, name, token):
        client = server.app.test_client()
        with client.session_transaction() as session:
            session['user_name'] = name
            session['jwt_token'] = token
        return client

    def test_health_static_and_authentication(self):
        client = server.app.test_client()
        self.assertEqual(client.get('/healthz').json, {'status': 'ok'})
        with client.get('/login') as response:
            self.assertEqual(response.status_code, 200)
        self.assertEqual(client.get('/').status_code, 302)
        for path in ('/status', '/factions', '/factions/Red%20Veil/mods'):
            self.assertEqual(client.get(path).status_code, 401)

    def test_each_user_sees_only_their_live_orders(self):
        def orders(token, _):
            return {'data': [{'id': 'alice-order', 'itemId': 'mod-1', 'type': 'sell'}] if 'alice' in token else []}
        with patch.object(server, 'get_orders', side_effect=orders):
            alice_mod = self.alice.get('/factions/Red%20Veil/mods').json['mods'][0]
            bob_mod = self.bob.get('/factions/Red%20Veil/mods').json['mods'][0]
        self.assertEqual(alice_mod['order_id'], 'alice-order')
        self.assertFalse(bob_mod['has_order'])

    def test_batch_is_async_and_lock_is_per_account(self):
        started, release = threading.Event(), threading.Event()
        def create(*_):
            started.set()
            release.wait(5)
            return {'created': 1, 'skipped': 0, 'failed': [], 'unprocessed': 0}
        body = {'factions': ['Red Veil'], 'platinum': 12}
        with patch.object(server, 'create_orders', side_effect=create):
            try:
                response = self.alice.post('/process', json=body)
                self.assertEqual(response.status_code, 202)
                self.assertTrue(started.wait(1))
                self.assertEqual(self.alice.post('/process', json=body).status_code, 409)
                self.assertTrue(self.alice.get('/status').json['operation_in_progress'])
                self.assertFalse(self.bob.get('/status').json['operation_in_progress'])
                self.assertIsNone(self.bob.get('/status').json['job'])
                self.assertEqual(self.bob.post('/process', json=body).status_code, 202)
            finally:
                release.set()
            for _ in range(100):
                if all(job['state'] != 'running' for job in server.operations.values()):
                    break
                time.sleep(0.01)
        self.assertEqual(self.alice.get('/status').json['job']['state'], 'complete')

    def test_creation_uses_each_accounts_live_orders(self):
        with patch.object(creator, 'get_orders', side_effect=[
            {'data': [{'itemId': 'mod-1', 'type': 'sell'}]}, {'data': []},
        ]), patch.object(creator, 'api_request') as mutation:
            first = creator.create_orders('JWT alice', 'https://example.test', CATALOGUE['mods'], ['Red Veil'], 12)
            second = creator.create_orders('JWT bob', 'https://example.test', CATALOGUE['mods'], ['Red Veil'], 12)
        self.assertEqual(first['skipped'], 1)
        self.assertEqual(second['created'], 1)
        self.assertEqual(mutation.call_args.kwargs['headers']['Authorization'], 'Bearer bob')

    def test_deletion_only_targets_authenticated_users_augment_sells(self):
        orders = {'data': [
            {'id': 'own-sell', 'itemId': 'mod-1', 'type': 'sell'},
            {'id': 'own-buy', 'itemId': 'mod-1', 'type': 'buy'},
            {'id': 'other-item', 'itemId': 'mod-2', 'type': 'sell'},
        ]}
        with patch.object(deleter, 'get_orders', return_value=orders), patch.object(deleter, 'api_request') as mutation:
            result = deleter.delete_matching_orders('JWT alice', 'https://example.test', CATALOGUE['mods'])
        self.assertEqual(result['deleted'], 1)
        self.assertEqual(mutation.call_count, 1)
        self.assertTrue(mutation.call_args.args[1].endswith('/own-sell'))

    def test_cross_origin_mutation_is_rejected(self):
        response = self.alice.post('/delete', headers={'Origin': 'https://another.example'})
        self.assertEqual(response.status_code, 403)

    def test_login_stores_no_password_and_logout_clears_auth(self):
        client = server.app.test_client()
        with patch.object(server, 'login', return_value=('Alice', 'JWT alice')):
            response = client.post('/api/login', json={'email': 'alice@example.test', 'password': 'test-password'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('HttpOnly', response.headers['Set-Cookie'])
        self.assertIn('SameSite=Lax', response.headers['Set-Cookie'])
        with client.session_transaction() as session:
            self.assertNotIn('password', session)
            self.assertEqual(session['jwt_token'], 'JWT alice')
        self.assertEqual(client.post('/logout').status_code, 200)
        self.assertEqual(client.get('/status').status_code, 401)

    def test_single_delete_verifies_ownership(self):
        with patch.object(server, 'get_orders', return_value={'data': []}), patch.object(server, 'api_request') as mutation:
            self.assertEqual(self.alice.delete('/api/mod/order/someone-elses-order').status_code, 404)
            mutation.assert_not_called()

    def test_single_operation_does_not_overwrite_batch_result(self):
        with server.app.test_request_context():
            batch, _ = server.reserve_operation('alice', 'create')
            server.finish_operation('alice', batch, state='complete', message='Created one order')
            single, _ = server.reserve_operation('alice', 'single')
            server.finish_operation('alice', single, state='complete')
        self.assertEqual(self.alice.get('/status').json['job']['id'], batch['id'])

    def test_prices_require_positive_integers(self):
        for value in (True, 0, -1, 1.5, '12', None):
            response = self.alice.post('/process', json={'factions': ['Red Veil'], 'platinum': value})
            self.assertEqual(response.status_code, 400)

    def test_failed_write_is_not_retried_and_partial_result_is_reported(self):
        mods = {'Red Veil': [
            {'Name': 'First', 'id': 'first'}, {'Name': 'Second', 'id': 'second'}, {'Name': 'Third', 'id': 'third'},
        ]}
        with patch.object(creator, 'get_orders', return_value={'data': []}), patch.object(
            creator, 'api_request', side_effect=[Mock(), requests.Timeout()],
        ) as mutation:
            result = creator.create_orders('JWT alice', 'https://example.test', mods, ['Red Veil'], 12)
        self.assertEqual(result['created'], 1)
        self.assertEqual(result['failed'], ['Second'])
        self.assertEqual(result['unprocessed'], 1)
        self.assertEqual(mutation.call_count, 2)


if __name__ == '__main__':
    unittest.main()
