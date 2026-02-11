# WF Market V2 (Web UI)

This project is a small Flask web application to automate creating and deleting augment mod orders on Warframe Market.

## Requirements

- Python 3.8+
- Required Python packages: `flask`, `requests`, `python-dotenv`, `beautifulsoup4`

You can install them with:

```bash
pip install flask requests python-dotenv beautifulsoup4
```

## Running the app (development)

Run the Flask app directly:

```bash
python app.py
```

Open `http://localhost:5000` in your browser. The app will redirect you to `/login` if you're not authenticated.

## Web UI flow

- Visit `/login` and enter your Warframe Market email and password.
- On successful login the server stores the JWT in your session and redirects to the main UI.
- From the main UI you can:
  - Select a single syndicate
  - Enter a platinum amount (any value > 0)
  - Click **Create Orders** to create sell orders for that syndicate
  - Click **Delete Matching Orders** to remove existing orders that match the augment mods list

## Endpoints

- `GET /login` — login page
- `POST /api/login` — accepts JSON `{email, password}`; stores JWT in session on success
- `GET /` — main UI (requires login)
- `GET /factions` — returns available syndicates (requires login)
- `POST /process` — create orders for selected syndicate (requires login)
- `POST /delete` — delete matching orders (requires login)
- `GET /status` — returns whether an operation is in progress (requires login)
- `GET /logout` — clear session and go to login page

## Files

- `app.py` — Flask application and routes
- `templates/login.html` — login page
- `templates/index.html` — main UI
- `login.py` — wrapper that calls the Warframe Market signin API and returns `(username, jwt)` on success
- `get_all_items.py`, `get_orders.py`, `scrape_syndicate_mods.py`, `create_orders.py`, `delete_orders.py` — core automation modules
- `augment_mods_by_syndicate.json`, `items.json`, `orders.json` — data files used by the app

## Running the app

1. Start the app:

```bash
python app.py
```

2. Open `http://localhost:5000/login`, sign in, then exercise the UI.