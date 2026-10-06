"""Shared outbound API pacing for the single Render worker."""

import threading
import time

import requests

_request_lock = threading.Lock()
_last_request = 0.0


def api_request(method, url, **kwargs):
    global _last_request
    # WFM permits three requests/second. Pace all users together, including login.
    with _request_lock:
        delay = 0.4 - (time.monotonic() - _last_request)
        if delay > 0:
            time.sleep(delay)
        _last_request = time.monotonic()
    kwargs.setdefault('timeout', (5, 20))
    headers = dict(kwargs.pop('headers', {}))
    headers.setdefault('User-Agent', 'WFMarketV2/2.0 (+https://wf-market-v2.onrender.com)')
    kwargs['headers'] = headers
    response = requests.request(method, url, **kwargs)
    response.raise_for_status()
    return response


def auth_headers(token, platform='pc', language='en'):
    return {
        'Accept': 'application/json',
        'Authorization': token.replace('JWT', 'Bearer', 1),
        'platform': platform,
        'language': language,
    }
