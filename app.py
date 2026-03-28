import os
import json
from flask import Flask, request, jsonify, session, redirect, url_for, send_from_directory
from functools import wraps
import threading

from get_all_items import get_all_items as func_get_all_items
from get_orders import get_orders as func_get_orders
from scrape_syndicate_mods import scrape_syndicate_mods
from login import login
from create_orders import create_orders
from delete_orders import delete_matching_orders

# Serve React build from static/react
REACT_BUILD = os.path.join(os.path.dirname(__file__), 'static', 'react')

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
        with open('augment_mods_by_syndicate.json', 'r', encoding='utf-8') as f:
            mods_data = json.load(f)
        return list(mods_data.keys())
    except FileNotFoundError:
        return []

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
        with open('orders.json', 'w', encoding='utf-8') as f:
            json.dump(orders_data, f, indent=4)
        
        # Delete matching orders
        delete_matching_orders(jwt_token, WFM_API)
        
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
        with open('items.json', 'w', encoding='utf-8') as f:
            json.dump(items_data, f, indent=4)
        
        orders_data = func_get_orders(jwt_token, WFM_API)
        with open('orders.json', 'w', encoding='utf-8') as f:
            json.dump(orders_data, f, indent=4)
        
        # Update augments and process orders
        scrape_syndicate_mods()
        create_orders(jwt_token, WFM_API, syndicates=factions, platinum=platinum)
        
        return jsonify({'success': True, 'message': f'Orders processed for {", ".join(factions)} with {platinum} platinum'}), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
    finally:
        with operation_lock:
            operation_in_progress = False

if __name__ == '__main__':
    app.run(debug=True)
