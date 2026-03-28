# WF Market V2

A React + Flask web application that automates creating and deleting Warframe Augment Mod sell orders on [Warframe Market](https://warframe.market).

## Project Structure

```
backend/                          # Python / Flask server
  app.py                          # Flask app, all routes
  login.py                        # WFM sign-in wrapper
  get_all_items.py                 # Fetch full item catalogue from WFM API
  get_orders.py                   # Fetch current user orders from WFM API
  scrape_syndicate_mods.py        # Scrape augment mod list from the Warframe wiki
  create_orders.py                # Batch-create sell orders for a syndicate
  delete_orders.py                # Delete existing orders that match augment mods

frontend/                         # React + Vite source
  src/
    pages/
      Login.jsx                   # Login page
      Dashboard.jsx               # Main dashboard (batch + individual tabs)
    components/
      ModGrid.jsx                 # Per-mod grid with thumbnails and individual ordering

static/react/                     # Built React app served by Flask (git-ignored)
data/                             # Runtime-generated JSON files (git-ignored)
  items.json                      # Full WFM item catalogue (refreshed on login)
  orders.json                     # User orders snapshot
  augment_mods_by_syndicate.json  # Scraped augment mod data with item IDs
```

## Requirements

### Backend
- Python 3.8+
- `flask requests beautifulsoup4`

```bash
pip install flask requests beautifulsoup4
```

### Frontend (only needed to rebuild the React app)
- Node.js 18+

```bash
cd frontend
npm install
```

## Running

### Production (using the pre-built React app)

```bash
python backend/app.py
```

Open `http://localhost:5000`. Flask serves the built React app from `static/react/`.

### Development (Vite dev server with hot reload)

Terminal 1 — Flask backend:
```bash
python backend/app.py
```

Terminal 2 — Vite dev server:
```bash
cd frontend
npm run dev
```

Open `http://localhost:3000`. Vite proxies all API requests to Flask on port 5000.

To rebuild the React app after frontend changes:
```bash
cd frontend
npm run build
```

## Usage

1. Open the app and sign in with your Warframe Market account credentials.
2. After login the server bootstraps automatically in the background — it fetches the full item catalogue and scrapes the augment mod list from the Warframe wiki so all mod IDs are resolved before you interact with the UI.
3. **Batch tab** — select one or more syndicates, set a platinum price, then click **Create Orders** or **Delete Matching Orders** to act on all mods for those syndicates at once.
4. **Individual Mods tab** — pick a syndicate, browse or search mods by name, and list individual mods at your chosen price. After each order is placed the list re-fetches from the server so the "Listed" badge reflects the real state.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/login` | Serve React app (login route) |
| `POST` | `/api/login` | `{email, password}` — stores JWT in session on success |
| `GET` | `/logout` | Clear session and redirect to login |
| `GET` | `/` | Serve React app (dashboard) |
| `GET` | `/status` | Returns `{operation_in_progress: bool}` |
| `GET` | `/factions` | List available syndicates |
| `GET` | `/factions/<name>/mods` | Mods for a syndicate with thumbnail URLs and order status |
| `POST` | `/process` | Batch-create orders — body: `{factions, platinum}` |
| `POST` | `/delete` | Delete all orders matching augment mod IDs |
| `POST` | `/api/mod/order` | Create a single order — body: `{item_id, platinum}` |
| `DELETE` | `/api/mod/order/<id>` | Delete a single order by ID |
