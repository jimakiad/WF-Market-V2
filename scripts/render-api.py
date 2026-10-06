"""Deployment helper. Supply a Render API key via environment or standard input.

Never saves credentials or prints service environment-variable values.
"""
import json
import os
import secrets
import sys

import requests

token = os.environ.get('RENDER_API_KEY') or sys.stdin.readline().strip()
if not token:
    raise SystemExit('A Render API key is required')

method, path = sys.argv[1:3]
body = None
if method == 'POST' and path == '/services':
    body = {
        'type': 'web_service', 'name': 'wf-market-v2', 'ownerId': sys.argv[3],
        'repo': 'https://github.com/jimakiad/WF-Market-V2', 'branch': 'main',
        'autoDeployTrigger': 'commit',
        'serviceDetails': {
            'runtime': 'python', 'plan': 'free', 'region': 'frankfurt',
            'healthCheckPath': '/healthz',
            'envSpecificDetails': {
                'buildCommand': 'bash scripts/render-build.sh',
                'startCommand': 'gunicorn --chdir backend app:app --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 60 --access-logfile - --error-logfile -',
            },
        },
        'envVars': [
            {'key': 'SECRET_KEY', 'value': secrets.token_hex(32)},
            {'key': 'SESSION_COOKIE_SECURE', 'value': 'true'},
            {'key': 'PYTHONUNBUFFERED', 'value': '1'},
        ],
    }
elif method == 'POST':
    body = {}

response = requests.request(method, 'https://api.render.com/v1' + path,
                            headers={'Authorization': 'Bearer ' + token}, json=body, timeout=30)
print('HTTP', response.status_code)
try:
    result = response.json()
except ValueError:
    print('Render returned a non-JSON response')
    raise SystemExit(1)


def redact(value):
    if isinstance(value, dict):
        return {key: '[redacted]' if key.lower() in ('envvars', 'secret', 'authorization') or (key == 'value' and 'key' in value)
                else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return value.replace(token, '[redacted]')
    return value


print(json.dumps(redact(result)))
if not response.ok:
    raise SystemExit(1)
