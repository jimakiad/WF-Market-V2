import os
import sys
import subprocess
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backend'))
import app as server
from security import LoginLimiter, SessionStore, client_address
import wfm_client


class AuthenticationSecurityTests(unittest.TestCase):
    def setUp(self):
        server.app.config.update(TESTING=True, SECRET_KEY='test-secret', SESSION_COOKIE_SECURE=False)
        server.auth_sessions = SessionStore()
        server.login_limiter = LoginLimiter()
        server.operations.clear()
        server.batch_jobs.clear()
        self.client = server.app.test_client()

    def login(self, client=None, email='alice@example.test', address='203.0.113.1', headers=None):
        with patch.object(server, 'login', return_value=('Alice', 'JWT test-token')):
            return (client or self.client).post('/api/login',
                json={'email': email, 'password': 'test-password'},
                environ_overrides={'REMOTE_ADDR': address}, headers=headers or {})

    def test_logout_revokes_copied_cookie(self):
        self.assertEqual(self.login().status_code, 200)
        copied = self.client.get_cookie('session').value
        self.client.post('/logout')
        replay = server.app.test_client()
        replay.set_cookie('session', copied)
        self.assertEqual(replay.get('/status').status_code, 401)
        with patch.object(server, 'api_request') as upstream:
            self.assertEqual(replay.post('/api/mod/order', json={'item_id': 'test-mod', 'platinum': 12}).status_code, 401)
            upstream.assert_not_called()

    def test_cookie_contains_only_opaque_id_and_no_token_or_identity(self):
        self.login()
        cookie = self.client.get_cookie('session').value
        decoded = server.app.session_interface.get_signing_serializer(server.app).loads(cookie)
        self.assertEqual(set(decoded), {'session_id', '_permanent'})
        self.assertEqual(len(decoded['session_id']), 43)
        self.assertEqual(server.auth_sessions.get(decoded['session_id'])['jwt_token'], 'JWT test-token')

    def test_new_login_rotates_and_revokes_previous_cookie(self):
        self.login()
        copied = self.client.get_cookie('session').value
        self.login()
        self.assertNotEqual(copied, self.client.get_cookie('session').value)
        replay = server.app.test_client()
        replay.set_cookie('session', copied)
        self.assertEqual(replay.get('/status').status_code, 401)
        self.assertEqual(self.client.get('/status').status_code, 200)

    def test_expired_session_cannot_access_or_mutate(self):
        now = [0]
        server.auth_sessions = SessionStore(lifetime=10, clock=lambda: now[0])
        self.login()
        now[0] = 10
        self.assertEqual(self.client.get('/status').status_code, 401)
        self.assertEqual(self.client.post('/delete').status_code, 401)

    def test_expiry_is_absolute_despite_intervening_requests(self):
        now = [0]
        server.auth_sessions = SessionStore(lifetime=10, clock=lambda: now[0])
        self.login()
        now[0] = 9
        self.assertEqual(self.client.get('/status').status_code, 200)
        now[0] = 11
        self.assertEqual(self.client.get('/status').status_code, 401)

    def test_restart_and_legacy_cookies_fail_closed(self):
        self.login()
        server.auth_sessions = SessionStore()
        self.assertEqual(self.client.get('/status').status_code, 401)
        with self.client.session_transaction() as session:
            session['user_name'] = 'Alice'
            session['jwt_token'] = 'JWT legacy-token'
        self.assertEqual(self.client.get('/status').status_code, 401)

    def test_upstream_authentication_failure_revokes_session(self):
        self.login()
        copied = self.client.get_cookie('session').value
        response = requests.Response()
        response.status_code = 401
        with patch.object(server, 'get_catalogue', return_value={'mods': {'Test': [{'id': 'test-mod'}]}}), patch.object(
            server, 'api_request', side_effect=requests.HTTPError(response=response),
        ):
            self.assertEqual(self.client.post('/api/mod/order', json={'item_id': 'test-mod', 'platinum': 12}).status_code, 401)
        replay = server.app.test_client()
        replay.set_cookie('session', copied)
        self.assertEqual(replay.get('/status').status_code, 401)

    def test_failed_sign_in_does_not_revoke_existing_session(self):
        self.login()
        response = requests.Response()
        response.status_code = 401
        with patch.object(server, 'login', side_effect=requests.HTTPError(response=response)):
            self.assertEqual(self.client.post('/api/login', json={'email': 'alice@example.test', 'password': 'test-wrong'}).status_code, 401)
        self.assertEqual(self.client.get('/status').status_code, 200)

    def test_account_limit_applies_across_ips_and_email_case(self):
        with patch.object(server, 'login', return_value=(None, None)) as upstream:
            for index in range(5):
                response = self.client.post('/api/login', json={
                    'email': ' Alice@Example.Test ' if index % 2 else 'alice@example.test',
                    'password': 'test-wrong',
                }, environ_overrides={'REMOTE_ADDR': f'203.0.113.{index + 1}'})
                self.assertEqual(response.status_code, 401)
            response = self.client.post('/api/login', json={'email': 'alice@example.test', 'password': 'test-wrong'})
            self.assertEqual(response.status_code, 429)
            self.assertGreater(int(response.headers['Retry-After']), 0)
            self.assertEqual(upstream.call_count, 5)

    def test_client_limit_applies_across_accounts_and_spoofed_headers(self):
        with patch.object(server, 'login', return_value=(None, None)) as upstream:
            for index in range(20):
                response = self.client.post('/api/login', json={
                    'email': f'audit-{index}@example.test', 'password': 'test-wrong',
                }, headers={'X-Forwarded-For': f'203.0.113.{index + 1}'})
                self.assertEqual(response.status_code, 401)
            response = self.client.post('/api/login', json={'email': 'another@example.test', 'password': 'test-wrong'},
                                        headers={'X-Forwarded-For': '198.51.100.3'})
            self.assertEqual(response.status_code, 429)
            self.assertEqual(upstream.call_count, 20)

    def test_limits_expire_and_retry_after_decreases(self):
        now = [0]
        server.login_limiter = LoginLimiter(account_limit=1, window=30, clock=lambda: now[0])
        self.login()
        now[0] = 10
        blocked = self.login()
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked.headers['Retry-After'], '20')
        now[0] = 30
        self.assertEqual(self.login().status_code, 200)

    def test_sessions_at_capacity_do_not_evict_valid_users(self):
        server.auth_sessions = SessionStore(max_sessions=1)
        self.assertEqual(self.login().status_code, 200)
        other = server.app.test_client()
        self.assertEqual(self.login(other, email='bob@example.test').status_code, 503)
        self.assertEqual(self.client.get('/status').status_code, 200)
        self.assertEqual(self.login().status_code, 200)

    def test_limiter_memory_exhaustion_does_not_reset_existing_counters(self):
        limiter = LoginLimiter(account_limit=1, max_keys=2)
        self.assertEqual(limiter.consume('alice@example.test', '203.0.113.1'), 0)
        self.assertGreater(limiter.consume('bob@example.test', '203.0.113.2'), 0)
        self.assertGreater(limiter.consume('alice@example.test', '203.0.113.1'), 0)

    def test_expired_sessions_free_capacity(self):
        now = [0]
        store = SessionStore(lifetime=10, max_sessions=1, clock=lambda: now[0])
        old = store.create('Alice', 'JWT test')
        self.assertIsNone(store.create('Bob', 'JWT test'))
        now[0] = 10
        self.assertIsNotNone(store.create('Bob', 'JWT test'))
        self.assertIsNone(store.get(old))

    def test_secure_cookie_and_browser_headers(self):
        server.app.config['SESSION_COOKIE_SECURE'] = True
        with patch.object(server, 'login', return_value=('Alice', 'JWT test-token')):
            response = self.client.post('/api/login', base_url='https://localhost',
                json={'email': 'alice@example.test', 'password': 'test-password'},
                headers={'Origin': 'https://localhost'})
        self.assertIn('Secure', response.headers['Set-Cookie'])
        self.assertIn('HttpOnly', response.headers['Set-Cookie'])
        self.assertIn('SameSite=Lax', response.headers['Set-Cookie'])
        self.assertEqual(response.headers['Strict-Transport-Security'], 'max-age=31536000')
        policy = response.headers['Content-Security-Policy']
        self.assertIn("script-src 'self'", policy)
        self.assertIn("frame-ancestors 'none'", policy)
        self.assertIn('https://fonts.googleapis.com', policy)
        self.assertIn('https://*.warframe.market', policy)
        self.assertNotIn('unsafe-inline', policy)
        self.assertNotIn('Strict-Transport-Security', self.client.get('/healthz', base_url='http://localhost').headers)

    def test_origin_validation_rejects_other_schemes_and_malformed_origins(self):
        with patch.object(server, 'login') as upstream:
            for origin in ('http://localhost', 'https://[', 'null', 'https://localhost/path'):
                response = self.client.post('/api/login', base_url='https://localhost', json={}, headers={'Origin': origin})
                self.assertEqual(response.status_code, 403)
            upstream.assert_not_called()

    def test_render_client_address_ignores_spoofed_left_entries(self):
        forwarded = '198.51.100.50, 203.0.113.8, 104.16.1.1, 10.0.0.2'
        self.assertEqual(client_address('10.0.0.3', forwarded, True), '203.0.113.8')
        self.assertEqual(client_address('10.0.0.3', forwarded, False), '10.0.0.3')
        self.assertEqual(client_address('203.0.113.8', '198.51.100.50', True), '203.0.113.8')
        self.assertEqual(client_address('10.0.0.3', 'malformed', True), '10.0.0.3')
        self.assertEqual(client_address('10.0.0.3', None, True), '10.0.0.3')
        self.assertEqual(client_address('10.0.0.3', ','.join(['203.0.113.8'] * 33), True), '10.0.0.3')

    def test_render_ipv6_chain_and_mapped_addresses_are_normalized(self):
        self.assertEqual(client_address('10.0.0.3', '2001:db8::2, 2606:4700::1', True), '2001:db8::2')
        self.assertEqual(client_address('::ffff:203.0.113.8', '198.51.100.50', False), '203.0.113.8')

    def test_render_headers_cannot_bypass_client_limits(self):
        server.login_limiter = LoginLimiter(client_limit=2)
        with patch.object(server, 'ON_RENDER', True), patch.object(server, 'login', return_value=(None, None)) as upstream:
            for index in range(3):
                response = self.client.post('/api/login', json={
                    'email': f'audit-{index}@example.test', 'password': 'test-wrong',
                }, headers={'X-Forwarded-For': f'198.51.100.{index}, 203.0.113.8, 104.16.1.1'},
                   environ_overrides={'REMOTE_ADDR': '10.0.0.2'})
                self.assertEqual(response.status_code, 401 if index < 2 else 429)
            self.assertEqual(upstream.call_count, 2)

    def test_concurrent_attempts_cannot_bypass_account_limit(self):
        limiter = LoginLimiter()
        with ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(lambda index: limiter.consume('alice@example.test', f'203.0.113.{index}'), range(20)))
        self.assertEqual(results.count(0), 5)

    def test_render_configuration_preserves_tcp_peer_and_secure_cookies(self):
        env = dict(os.environ, RENDER='true', SECRET_KEY='configuration-test-only-secret',
                   SESSION_COOKIE_SECURE='true', PYTHONPATH=os.path.abspath('backend'))
        result = subprocess.run([sys.executable, '-c',
            "import app; assert app.ON_RENDER; assert app.app.wsgi_app.x_for == 0; "
            "assert app.app.wsgi_app.x_proto == 1; assert app.app.config['SESSION_COOKIE_SECURE']"],
            env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_api_requests_identify_application_without_credentials_in_user_agent(self):
        with patch.object(wfm_client.requests, 'request') as upstream, patch.object(wfm_client.time, 'sleep'):
            wfm_client.api_request('GET', 'https://api.warframe.market/v2/items', headers={'Accept': 'application/json'})
        headers = upstream.call_args.kwargs['headers']
        self.assertEqual(headers['Accept'], 'application/json')
        self.assertEqual(headers['User-Agent'], 'WFMarketV2/2.0 (+https://wf-market-v2.onrender.com)')


if __name__ == '__main__':
    unittest.main()
