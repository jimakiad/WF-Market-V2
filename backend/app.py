import os
import sys
import json
import requests as http_requests
from flask import Flask, request, jsonify, session, redirect, url_for, send_from_directory
from functools import wraps
import threading

# Ensure sibling modules (get_all_items, login, etc.) are importable regardless
# of where the process is launched from (project root or backend/).
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from get_all_items import get_all_items as func_get_all_items
from get_orders import get_orders as func_get_orders
from scrape_syndicate_mods import scrape_syndicate_mods
from login import login
from create_orders import create_orders
from delete_orders import delete_matching_orders

# Anchor all paths to the project root (one level above this file)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
REACT_BUILD = os.path.join(BASE_DIR, 'static', 'react')

app = Flask(__name__, static_folder=REACT_BUILD, static_url_path='')
app.secret_key = os.urandom(24)

WFM_API = "https://api.warframe.market"

if not WFM_API:
    raise RuntimeError("Missing required environment variable: WFM_API")

JWT = None
operation_lock = threading.Lock()
operation_in_progress = False

# initialize_jwt removed — authentication must be performed via the login page

def require_login(f):
    """Decorator to require user to be logged in"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_logged_in' not in session:
            # For API requests, return 401 so the React app can redirect
            if request.path.startswith('/api') or request.is_json or request.headers.get('Accept') == 'application/json':
                return jsonify({'error': 'Not authenticated'}), 401
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

def get_available_factions():
    """Load available factions from augment_mods_by_syndicate.json"""
    try:
        with open(os.path.join(DATA_DIR, 'augment_mods_by_syndicate.json'), 'r', encoding='utf-8') as f:
            mods_data = json.load(f)
        return list(mods_data.keys())
    except FileNotFoundError:
        return []

def _bootstrap(jwt_token: str):
    """Fetch all items + scrape syndicate mods after login so item IDs are populated."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        items_data = func_get_all_items(jwt_token, WFM_API)
        if items_data:
            with open(os.path.join(DATA_DIR, 'items.json'), 'w', encoding='utf-8') as f:
                json.dump(items_data, f, indent=4)
            scrape_syndicate_mods()
    except Exception as exc:
        print(f'[bootstrap] {exc}')


def _refresh_orders_async(jwt_token: str):
    """Fetch the latest user orders from WFM and persist to orders.json."""
    def _run():
        try:
            data = func_get_orders(jwt_token, WFM_API)
            if data:
                with open(os.path.join(DATA_DIR, 'orders.json'), 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4)
        except Exception as exc:
            print(f'[refresh_orders] {exc}')
    threading.Thread(target=_run, daemon=True).start()


@app.route('/login', methods=['GET'])
def login_page():
    """Serve React app for login"""
    return send_from_directory(REACT_BUILD, 'index.html')

@app.route('/api/login', methods=['POST'])
def api_login():
    """Handle login"""
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        
        if not email or not password:
            return jsonify({'error': 'Email and password required'}), 400
        
        # Try to login with provided credentials
        user_name, jwt_token = login(email, password, WFM_API)
        
        if jwt_token:
            session['user_logged_in'] = True
            session['user_email'] = email
            session['jwt_token'] = jwt_token
            # Bootstrap item + mod data in the background so IDs are always fresh
            threading.Thread(target=_bootstrap, args=(jwt_token,), daemon=True).start()
            return jsonify({'success': True}), 200
        else:
            return jsonify({'error': 'Invalid credentials'}), 401
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/logout', methods=['GET'])
def logout():
    """Logout user"""
    session.clear()
    return redirect(url_for('login_page'))

@app.route('/')
@require_login
def index():
    return send_from_directory(REACT_BUILD, 'index.html')

@app.route('/status', methods=['GET'])
@require_login
def get_status():
    """Check if an operation is in progress"""
    return jsonify({'operation_in_progress': operation_in_progress}), 200

@app.route('/factions', methods=['GET'])
@require_login
def get_factions():
    """Return available factions"""
    try:
        factions = get_available_factions()
        return jsonify({'factions': factions}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/factions/<faction_name>/mods', methods=['GET'])
@require_login
def get_faction_mods(faction_name):
    """Return mods for a specific faction with thumbnail URLs and live order status"""
    jwt_token = session.get('jwt_token')
    try:
        with open(os.path.join(DATA_DIR, 'augment_mods_by_syndicate.json'), 'r', encoding='utf-8') as f:
            mods_data = json.load(f)

        if faction_name not in mods_data:
            return jsonify({'error': 'Faction not found'}), 404

        # Build id->thumb lookup from items.json
        thumb_map = {}
        try:
            with open(os.path.join(DATA_DIR, 'items.json'), 'r', encoding='utf-8') as f:
                items = json.load(f).get('data', [])
            for item in items:
                i18n = item.get('i18n', {}).get('en', {})
                if i18n.get('thumb'):
                    thumb_map[item['id']] = f"https://warframe.market/static/assets/{i18n['thumb']}"
        except FileNotFoundError:
            pass

        # Fetch live sell orders from WFM — this is the single source of truth
        live_order_map = {}  # item_id -> order_id
        try:
            orders_data = func_get_orders(jwt_token, WFM_API)
            for order in orders_data.get('data', []):
                if order.get('type') == 'sell':
                    live_order_map[order['itemId']] = order['id']
        except Exception:
            pass

        mods = []
        for mod in mods_data[faction_name]:
            mod_id = mod.get('id')
            order_id = live_order_map.get(mod_id) if mod_id else None
            mod_entry = {
                'name': mod.get('Name', ''),
                'url_name': mod.get('URL_Name', ''),
                'id': mod_id,
                'has_order': order_id is not None,
                'order_id': order_id,
                'thumb': thumb_map.get(mod_id, ''),
            }
            mods.append(mod_entry)

        return jsonify({'faction': faction_name, 'mods': mods}), 200
    except FileNotFoundError:
        return jsonify({'error': 'Mod data not available. Run a syndicate process first.'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/delete', methods=['POST'])
@require_login
def delete_orders():
    """Delete matching orders"""
    global operation_in_progress, JWT
    
    if operation_in_progress:
        return jsonify({'error': 'Operation already in progress'}), 409

    # Require JWT from session (login page must provide it)
    jwt_token = session.get('jwt_token')
    if not jwt_token:
        return jsonify({'error': 'Not authenticated'},), 401

    try:
        with operation_lock:
            operation_in_progress = True
        
        # Fetch latest orders data
        orders_data = func_get_orders(jwt_token, WFM_API)
        with open(os.path.join(DATA_DIR, 'orders.json'), 'w', encoding='utf-8') as f:
            json.dump(orders_data, f, indent=4)
        
        # Delete matching orders
        delete_matching_orders(jwt_token, WFM_API)

        # Refresh orders.json to reflect deletions
        try:
            fresh = func_get_orders(jwt_token, WFM_API)
            if fresh:
                with open(os.path.join(DATA_DIR, 'orders.json'), 'w', encoding='utf-8') as f:
                    json.dump(fresh, f, indent=4)
        except Exception:
            pass

        return jsonify({'success': True, 'message': 'Matching orders deleted successfully'}), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
    finally:
        with operation_lock:
            operation_in_progress = False

@app.route('/process', methods=['POST'])
@require_login
def process_order():
    """Create orders for selected syndicates"""
    global operation_in_progress, JWT
    
    if operation_in_progress:
        return jsonify({'error': 'Operation already in progress'}), 409
    
    try:
        with operation_lock:
            operation_in_progress = True
        
        data = request.get_json()
        factions = data.get('factions', [])
        platinum = data.get('platinum', 0)
        
        if not factions or platinum <= 0:
            return jsonify({'error': 'Please select at least one faction and enter a valid platinum amount'}), 400
        
        # Validate factions
        available_factions = get_available_factions()
        invalid_factions = [f for f in factions if f not in available_factions]
        if invalid_factions:
            return jsonify({'error': f'Invalid factions: {", ".join(invalid_factions)}'}), 400
        
        # Require JWT from session (login page must provide it)
        jwt_token = session.get('jwt_token')
        if not jwt_token:
            return jsonify({'error': 'Not authenticated'},), 401
        
        # Fetch latest data
        items_data = func_get_all_items(jwt_token, WFM_API)
        with open(os.path.join(DATA_DIR, 'items.json'), 'w', encoding='utf-8') as f:
            json.dump(items_data, f, indent=4)
        
        orders_data = func_get_orders(jwt_token, WFM_API)
        with open(os.path.join(DATA_DIR, 'orders.json'), 'w', encoding='utf-8') as f:
            json.dump(orders_data, f, indent=4)
        
        # Update augments and process orders
        scrape_syndicate_mods()
        create_orders(jwt_token, WFM_API, syndicates=factions, platinum=platinum)

        # Refresh orders.json to reflect newly created orders
        try:
            fresh = func_get_orders(jwt_token, WFM_API)
            if fresh:
                with open(os.path.join(DATA_DIR, 'orders.json'), 'w', encoding='utf-8') as f:
                    json.dump(fresh, f, indent=4)
        except Exception:
            pass

        return jsonify({'success': True, 'message': f'Orders processed for {", ".join(factions)} with {platinum} platinum'}), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
    finally:
        with operation_lock:
            operation_in_progress = False

@app.route('/api/mod/order', methods=['POST'])
@require_login
def create_single_mod_order():
    """Create a sell order for a single mod by item ID"""
    jwt_token = session.get('jwt_token')
    if not jwt_token:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.get_json()
    item_id = data.get('item_id')
    platinum = data.get('platinum', 12)

    if not item_id:
        return jsonify({'error': 'item_id is required'}), 400
    if platinum <= 0:
        return jsonify({'error': 'Platinum must be > 0'}), 400

    headers = {
        "Accept": "application/json",
        "Authorization": jwt_token.replace("JWT", "Bearer"),
        "platform": "pc",
        "language": "en",
    }
    body = {
        "itemId": item_id,
        "type": "sell",
        "platinum": platinum,
        "quantity": 1,
        "visible": True,
        "rank": 0,
    }

    try:
        resp = http_requests.post(f"{WFM_API}/v2/order", json=body, headers=headers)
        resp.raise_for_status()
        result = resp.json()
        order_id = result.get('data', {}).get('id')

        # Persist orderId into augment_mods_by_syndicate.json so re-fetch shows correct status
        if order_id:
            augment_path = os.path.join(DATA_DIR, 'augment_mods_by_syndicate.json')
            try:
                with open(augment_path, 'r', encoding='utf-8') as f:
                    augment_data = json.load(f)
                for mods_list in augment_data.values():
                    for mod in mods_list:
                        if mod.get('id') == item_id:
                            mod['orderId'] = order_id
                with open(augment_path, 'w', encoding='utf-8') as f:
                    json.dump(augment_data, f, indent=4, ensure_ascii=False)
            except Exception:
                pass  # non-fatal — order was created, persistence is best-effort

        return jsonify({'success': True, 'order_id': order_id}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    finally:
        # Keep orders.json in sync after creation
        _refresh_orders_async(jwt_token)

@app.route('/api/mod/order/<order_id>', methods=['DELETE'])
@require_login
def delete_single_mod_order(order_id):
    """Delete a single order by order ID"""
    jwt_token = session.get('jwt_token')
    if not jwt_token:
        return jsonify({'error': 'Not authenticated'}), 401

    headers = {
        "Accept": "application/json",
        "Authorization": jwt_token.replace("JWT", "Bearer"),
        "platform": "pc",
        "language": "en",
    }

    try:
        resp = http_requests.delete(f"{WFM_API}/v2/order/{order_id}", headers=headers)
        resp.raise_for_status()

        # Remove the stale orderId from augment JSON so the fallback path is clean
        augment_path = os.path.join(DATA_DIR, 'augment_mods_by_syndicate.json')
        try:
            with open(augment_path, 'r', encoding='utf-8') as f:
                augment_data = json.load(f)
            for mods_list in augment_data.values():
                for mod in mods_list:
                    if mod.get('orderId') == order_id:
                        del mod['orderId']
                        break
            with open(augment_path, 'w', encoding='utf-8') as f:
                json.dump(augment_data, f, indent=4, ensure_ascii=False)
        except Exception:
            pass  # non-fatal

        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        # Keep orders.json in sync after deletion
        _refresh_orders_async(jwt_token)

if __name__ == '__main__':
    os.makedirs(DATA_DIR, exist_ok=True)
    app.run(debug=True, use_reloader=False)
