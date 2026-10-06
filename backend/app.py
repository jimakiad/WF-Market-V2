import os
import sys
import threading
import time
import uuid
from datetime import timedelta
from functools import wraps
from urllib.parse import urlsplit

import requests
from flask import Flask, g, jsonify, redirect, request, send_from_directory, session, url_for
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from create_orders import create_orders
from delete_orders import delete_matching_orders
from get_all_items import get_all_items
from get_orders import get_orders
from login import login
from scrape_syndicate_mods import scrape_syndicate_mods
from wfm_client import api_request, auth_headers
from security import LoginLimiter, SessionStore, client_address

BASE_DIR = os.path.dirname(_BACKEND_DIR)
REACT_BUILD = os.path.join(BASE_DIR, 'static', 'react')
WFM_API = 'https://api.warframe.market'
ON_RENDER = os.environ.get('RENDER') == 'true'
secret_key = os.environ.get('SECRET_KEY')
if ON_RENDER and not secret_key:
    raise RuntimeError('SECRET_KEY must be configured on Render')

app = Flask(__name__, static_folder=REACT_BUILD, static_url_path='')
app.config.update(
    SECRET_KEY=secret_key or os.urandom(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=os.environ.get('SESSION_COOKIE_SECURE', str(ON_RENDER)).lower() == 'true',
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
    MAX_CONTENT_LENGTH=16 * 1024,
    SESSION_REFRESH_EACH_REQUEST=False,
)
if ON_RENDER:
    # Client addresses are resolved separately from the trusted side of the chain.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=0, x_proto=1)

# Only public catalogue data is shared. User orders always come from WFM.
catalogue_lock = threading.Lock()
catalogue = None
catalogue_updated = 0.0
operations_lock = threading.Lock()
operations = {}
batch_jobs = {}
login_slots = threading.BoundedSemaphore(2)
auth_sessions = SessionStore()
login_limiter = LoginLimiter()
MAX_ACTIVE_OPERATIONS = 8


def require_login(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        auth = auth_sessions.get(session.get('session_id'))
        if auth is None:
            session.clear()
            if request.path == '/':
                return redirect(url_for('login_page'))
            return jsonify(error='Not authenticated'), 401
        g.auth = auth
        return func(*args, **kwargs)
    return wrapped


@app.before_request
def check_origin():
    # Old client-side JWT sessions must not survive this authentication migration.
    if 'jwt_token' in session or 'user_name' in session:
        session.clear()
    if request.method in ('POST', 'DELETE', 'PUT', 'PATCH'):
        origin = request.headers.get('Origin')
        if request.headers.get('Sec-Fetch-Site') == 'cross-site':
            return jsonify(error='Please use this website to perform this action'), 403
        expected = urlsplit(request.host_url)
        try:
            supplied = urlsplit(origin) if origin else None
        except ValueError:
            return jsonify(error='Please use this website to perform this action'), 403
        if supplied and (supplied.scheme != expected.scheme or supplied.netloc != expected.netloc
                         or supplied.path or supplied.query or supplied.fragment):
            return jsonify(error='Please use this website to perform this action'), 403


@app.after_request
def response_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; script-src 'self'; "
        "style-src 'self' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https://warframe.market https://*.warframe.market; "
        "connect-src 'self'; media-src 'self'; object-src 'none'; "
        "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    )
    if request.is_secure:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000'
    if request.path != '/healthz' and not request.path.startswith('/assets/'):
        response.headers['Cache-Control'] = 'no-store'
    return response


@app.errorhandler(requests.RequestException)
def upstream_error(error):
    status = getattr(error.response, 'status_code', None)
    if status in (401, 403):
        if request.endpoint != 'api_login':
            revoke_session()
        return jsonify(error='Warframe Market rejected authentication. Please sign in again.'), 401
    if status == 429:
        return jsonify(error='Warframe Market is busy. Please wait before trying again.'), 503
    return jsonify(error='Could not complete the Warframe Market request. Check your orders before retrying.'), 502


@app.errorhandler(HTTPException)
def http_error(error):
    return jsonify(error=error.description), error.code


def get_catalogue(token):
    global catalogue, catalogue_updated
    with catalogue_lock:
        if catalogue is None or time.monotonic() - catalogue_updated > 6 * 3600:
            try:
                items = get_all_items(token, WFM_API)['data']
                mods = scrape_syndicate_mods(items)
                thumbs = {
                    item['id']: f"https://warframe.market/static/assets/{item['i18n']['en']['thumb']}"
                    for item in items if item.get('i18n', {}).get('en', {}).get('thumb')
                }
                catalogue = {'mods': mods, 'thumbs': thumbs}
                catalogue_updated = time.monotonic()
            except Exception:
                if catalogue is None:
                    raise
                app.logger.warning('Catalogue refresh failed; using previous public catalogue')
        return catalogue


def account_id():
    return g.auth['user_name'].casefold()


def revoke_session():
    auth_sessions.revoke(session.get('session_id'))
    session.clear()


def reserve_operation(user, kind):
    now = time.monotonic()
    with operations_lock:
        for key in list(operations):
            entry = operations[key]
            if entry['state'] != 'running' and now - entry['updated'] > 3600:
                del operations[key]
        for key in list(batch_jobs):
            entry = batch_jobs[key]
            if entry['state'] != 'running' and now - entry['updated'] > 3600:
                del batch_jobs[key]
        if operations.get(user, {}).get('state') == 'running':
            return None, (jsonify(error='An operation is already running for your account'), 409)
        if sum(entry['state'] == 'running' for entry in operations.values()) >= MAX_ACTIVE_OPERATIONS:
            return None, (jsonify(error='The server is busy. Please try again shortly.'), 503)
        job = {'id': uuid.uuid4().hex, 'kind': kind, 'state': 'running', 'updated': now}
        operations[user] = job
        if kind != 'single':
            batch_jobs[user] = job
        return job, None


def finish_operation(user, job, **result):
    with operations_lock:
        if operations.get(user) is job:
            job.update(updated=time.monotonic(), **result)


def start_batch(user, token, kind, factions=None, platinum=None):
    job, error = reserve_operation(user, kind)
    if error:
        return error

    def run():
        try:
            mods = get_catalogue(token)['mods']
            if kind == 'create':
                result = create_orders(token, WFM_API, mods, factions, platinum)
                message = f"Created {result['created']} orders; skipped {result['skipped']} existing listings."
            else:
                result = delete_matching_orders(token, WFM_API, mods)
                message = f"Deleted {result['deleted']} augment sell orders."
            if result['failed']:
                message += ' The batch stopped after an unconfirmed request. Check your listings before retrying.'
            finish_operation(user, job, state='failed' if result['failed'] else 'complete', message=message, result=result)
        except Exception:
            app.logger.warning('Batch operation failed (%s)', kind)
            finish_operation(user, job, state='failed', message='The batch could not finish. Check your listings and sign in again before retrying.')

    threading.Thread(target=run, daemon=True).start()
    return jsonify(success=True, job_id=job['id'], message='Batch started'), 202


def positive_price(value):
    return isinstance(value, int) and not isinstance(value, bool) and 0 < value <= 1_000_000


@app.route('/healthz')
def health():
    return jsonify(status='ok'), 200


@app.route('/login')
def login_page():
    return send_from_directory(REACT_BUILD, 'index.html')


@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    if not isinstance(data, dict):
        return jsonify(error='Email and password required'), 400
    email, password = data.get('email'), data.get('password')
    if not isinstance(email, str) or not isinstance(password, str) or not email.strip() or not password:
        return jsonify(error='Email and password required'), 400
    address = client_address(request.remote_addr, request.headers.get('X-Forwarded-For'), ON_RENDER)
    retry_after = login_limiter.consume(email, address)
    if retry_after:
        response = jsonify(error='Too many sign-in attempts. Please try again later.')
        response.headers['Retry-After'] = str(retry_after)
        return response, 429
    if not login_slots.acquire(blocking=False):
        response = jsonify(error='Sign-in is busy. Please try again shortly.')
        response.headers['Retry-After'] = '5'
        return response, 429
    try:
        user_name, token = login(email.strip(), password, WFM_API)
    finally:
        login_slots.release()
    if not token or not user_name:
        return jsonify(error='Invalid credentials'), 401
    session_id = auth_sessions.create(user_name, token, replace_id=session.get('session_id'))
    if session_id is None:
        return jsonify(error='Sign-in is busy. Please try again later.'), 503
    session.clear()
    session.permanent = True
    session['session_id'] = session_id
    return jsonify(success=True)


@app.route('/logout', methods=['POST'])
def logout():
    revoke_session()
    return jsonify(success=True)


@app.route('/')
@require_login
def index():
    return send_from_directory(REACT_BUILD, 'index.html')


@app.route('/status')
@require_login
def status():
    with operations_lock:
        job = batch_jobs.get(account_id())
        active = operations.get(account_id(), {}).get('state') == 'running'
        public_job = {key: value for key, value in job.items() if key != 'updated'} if job else None
        return jsonify(operation_in_progress=active, job=public_job)


@app.route('/factions')
@require_login
def factions():
    try:
        return jsonify(factions=list(get_catalogue(g.auth['jwt_token'])['mods']))
    except requests.RequestException:
        raise
    except Exception:
        return jsonify(error='Could not load syndicate data. Please reload to try again.'), 503


@app.route('/factions/<faction_name>/mods')
@require_login
def faction_mods(faction_name):
    data = get_catalogue(g.auth['jwt_token'])
    if faction_name not in data['mods']:
        return jsonify(error='Faction not found'), 404
    orders = get_orders(g.auth['jwt_token'], WFM_API)['data']
    listed = {order['itemId']: order['id'] for order in orders if order.get('type') == 'sell'}
    return jsonify(faction=faction_name, mods=[{
        'name': mod['Name'], 'url_name': mod['URL_Name'], 'id': mod.get('id'),
        'has_order': mod.get('id') in listed, 'order_id': listed.get(mod.get('id')),
        'thumb': data['thumbs'].get(mod.get('id'), ''),
    } for mod in data['mods'][faction_name]])


@app.route('/process', methods=['POST'])
@require_login
def process():
    data = request.get_json()
    if not isinstance(data, dict):
        return jsonify(error='Select syndicates and enter a price'), 400
    selected, platinum = data.get('factions'), data.get('platinum')
    if not isinstance(selected, list) or not selected or not all(isinstance(name, str) for name in selected):
        return jsonify(error='Select at least one syndicate'), 400
    if not positive_price(platinum):
        return jsonify(error='Platinum must be a positive whole number'), 400
    mods = get_catalogue(g.auth['jwt_token'])['mods']
    if any(name not in mods for name in selected):
        return jsonify(error='Invalid syndicate'), 400
    return start_batch(account_id(), g.auth['jwt_token'], 'create', selected, platinum)


@app.route('/delete', methods=['POST'])
@require_login
def delete_batch():
    return start_batch(account_id(), g.auth['jwt_token'], 'delete')


@app.route('/api/mod/order', methods=['POST'])
@require_login
def create_single_order():
    data = request.get_json()
    if not isinstance(data, dict):
        return jsonify(error='Item and price required'), 400
    item_id, platinum = data.get('item_id'), data.get('platinum', 12)
    if not isinstance(item_id, str) or not item_id:
        return jsonify(error='item_id is required'), 400
    if not positive_price(platinum):
        return jsonify(error='Platinum must be a positive whole number'), 400
    user, token = account_id(), g.auth['jwt_token']
    job, error = reserve_operation(user, 'single')
    if error:
        return error
    try:
        response = api_request('POST', f'{WFM_API}/v2/order', headers=auth_headers(token), json={
            'itemId': item_id, 'type': 'sell', 'platinum': platinum,
            'quantity': 1, 'visible': True, 'rank': 0,
        })
        return jsonify(success=True, order_id=response.json()['data']['id'])
    finally:
        finish_operation(user, job, state='complete')


@app.route('/api/mod/order/<order_id>', methods=['DELETE'])
@require_login
def delete_single_order(order_id):
    user, token = account_id(), g.auth['jwt_token']
    job, error = reserve_operation(user, 'single')
    if error:
        return error
    try:
        orders = get_orders(token, WFM_API)['data']
        if not any(order.get('id') == order_id and order.get('type') == 'sell' for order in orders):
            return jsonify(error='Sell order not found for your account'), 404
        api_request('DELETE', f'{WFM_API}/v2/order/{order_id}', headers=auth_headers(token))
        return jsonify(success=True)
    finally:
        finish_operation(user, job, state='complete')


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=os.environ.get('FLASK_DEBUG') == '1', use_reloader=False)
