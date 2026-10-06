"""Bounded authentication state for the single-worker deployment."""

import hashlib
import ipaddress
import math
import secrets
import threading
import time
from collections import deque


class SessionStore:
    def __init__(self, lifetime=12 * 3600, max_sessions=1000, clock=None):
        self.lifetime = lifetime
        self.max_sessions = max_sessions
        self._clock = clock or time.monotonic
        self._sessions = {}
        self._lock = threading.Lock()

    def create(self, user_name, token, replace_id=None):
        now = self._clock()
        with self._lock:
            self._sessions = {key: value for key, value in self._sessions.items()
                              if value['expires'] > now}
            replacing = isinstance(replace_id, str) and replace_id in self._sessions
            if len(self._sessions) >= self.max_sessions and not replacing:
                return None
            session_id = secrets.token_urlsafe(32)
            if replacing:
                del self._sessions[replace_id]
            self._sessions[session_id] = {
                'user_name': user_name, 'jwt_token': token,
                'expires': now + self.lifetime,
            }
            return session_id

    def get(self, session_id):
        if not isinstance(session_id, str) or len(session_id) > 128:
            return None
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return None
            if entry['expires'] <= self._clock():
                del self._sessions[session_id]
                return None
            return dict(entry)

    def revoke(self, session_id):
        if isinstance(session_id, str):
            with self._lock:
                self._sessions.pop(session_id, None)


class LoginLimiter:
    def __init__(self, account_limit=5, client_limit=20, window=15 * 60,
                 max_keys=2000, clock=None):
        self.account_limit = account_limit
        self.client_limit = client_limit
        self.window = window
        self.max_keys = max_keys
        self._clock = clock or time.monotonic
        self._attempts = {}
        self._lock = threading.Lock()

    def consume(self, account, client):
        """Return zero if allowed, otherwise the Retry-After delay in seconds."""
        now = self._clock()
        # Do not retain email addresses or IP addresses in the limiter's keys.
        buckets = [
            (('account', hashlib.sha256(account.strip().casefold().encode()).digest()), self.account_limit),
            (('client', hashlib.sha256(client.encode()).digest()), self.client_limit),
        ]
        with self._lock:
            for key in list(self._attempts):
                attempts = self._attempts[key]
                while attempts and attempts[0] <= now - self.window:
                    attempts.popleft()
                if not attempts:
                    del self._attempts[key]
            retries = [math.ceil(self._attempts[key][0] + self.window - now)
                       for key, limit in buckets
                       if key in self._attempts and len(self._attempts[key]) >= limit]
            if retries:
                return max(1, max(retries))
            new_keys = sum(key not in self._attempts for key, _ in buckets)
            if len(self._attempts) + new_keys > self.max_keys:
                # Fail closed instead of evicting counters during an attack.
                return self.window
            for key, _ in buckets:
                self._attempts.setdefault(key, deque()).append(now)
            return 0


# Render forwards traffic through its internal ingress and Cloudflare.
# Walk X-Forwarded-For from that trusted side, never from client-supplied left entries.
# Cloudflare ranges verified against https://www.cloudflare.com/ips/ on 2026-10-06.
_INTERNAL_PROXIES = tuple(ipaddress.ip_network(value) for value in (
    '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '127.0.0.0/8',
    'fc00::/7', 'fe80::/10', '::1/128',
))
_CLOUDFLARE_PROXIES = tuple(ipaddress.ip_network(value) for value in (
    '173.245.48.0/20', '103.21.244.0/22', '103.22.200.0/22', '103.31.4.0/22',
    '141.101.64.0/18', '108.162.192.0/18', '190.93.240.0/20', '188.114.96.0/20',
    '197.234.240.0/22', '198.41.128.0/17', '162.158.0.0/15', '104.16.0.0/13',
    '104.24.0.0/14', '172.64.0.0/13', '131.0.72.0/22',
    '2400:cb00::/32', '2606:4700::/32', '2803:f800::/32', '2405:b500::/32',
    '2405:8100::/32', '2a06:98c0::/29', '2c0f:f248::/32',
))


def _address(value):
    address = ipaddress.ip_address(value.strip())
    return getattr(address, 'ipv4_mapped', None) or address


def client_address(remote_address, forwarded_for, on_render=False):
    try:
        peer = _address(remote_address or '')
    except ValueError:
        return 'unknown'
    trusted = _INTERNAL_PROXIES + _CLOUDFLARE_PROXIES
    if not on_render or not any(peer in network for network in trusted):
        return str(peer)
    hops = (forwarded_for or '').split(',')
    if len(hops) > 32:
        return str(peer)
    try:
        for value in reversed(hops):
            address = _address(value)
            if not any(address in network for network in trusted):
                return str(address)
    except ValueError:
        pass
    # Missing/malformed chains share the ingress bucket rather than bypass limits.
    return str(peer)
