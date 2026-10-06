# WF Market V2

A React + Flask web application that automates creating and deleting Warframe Augment Mod sell orders on [Warframe Market](https://warframe.market).

## Project Structure

```
backend/                          # Python / Flask server
  app.py                          # Flask app, all routes
  login.py                        # WFM sign-in wrapper
  wfm_client.py                   # Shared API pacing and request timeouts
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
render.yaml                       # Free Render service configuration
scripts/render-build.sh           # Builds Python dependencies and React on Render
tests/                            # Authentication, isolation, and operation tests
```

## Requirements

### Backend
- Python 3.12+

```bash
pip install -r requirements.txt
```

### Frontend (only needed to rebuild the React app)
- Node.js 22

```bash
cd frontend
npm install
```

## Running

### Local preview (build React first)

```bash
cd frontend
npm ci
npm run build
cd ..
```

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
2. The dashboard loads a public item and augment catalogue, cached in memory for six hours. Account orders are always fetched separately from Warframe Market.
3. **Batch tab** — select one or more syndicates, set a platinum price, then click **Create Orders** or **Delete Matching Orders** to act on all mods for those syndicates at once.
4. **Individual Mods tab** — pick a syndicate, browse or search mods by name, and list individual mods at your chosen price. After each order is placed the list re-fetches from the server so the "Listed" badge reflects the real state.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/login` | Serve React app (login route) |
| `POST` | `/api/login` | `{email, password}` — stores JWT in session on success |
| `POST` | `/logout` | Clear the session |
| `GET` | `/` | Serve React app (dashboard) |
| `GET` | `/healthz` | Public health check without upstream API calls |
| `GET` | `/status` | Current account operation and latest batch result |
| `GET` | `/factions` | List available syndicates |
| `GET` | `/factions/<name>/mods` | Mods for a syndicate with thumbnail URLs and order status |
| `POST` | `/process` | Start batch creation; returns `202` and `job_id` |
| `POST` | `/delete` | Start deletion of this account's matching augment sell orders |
| `POST` | `/api/mod/order` | Create a single order — body: `{item_id, platinum}` |
| `DELETE` | `/api/mod/order/<id>` | Delete a single order by ID |

## Deploy on Render for free

Connect this GitHub repository to Render and create a Blueprint using `render.yaml`.
It creates one Python web service on the **Free** plan in Frankfurt. The build
installs Python dependencies and compiles React; Gunicorn serves both the API
and the frontend. Render generates the session secret. No local PC or database
is required to run the deployed app.

For manual service creation, use:

- Runtime: Python
- Plan: Free
- Build command: `bash scripts/render-build.sh`
- Start command: `gunicorn --chdir backend app:app --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 60 --access-logfile - --error-logfile -`
- Health check: `/healthz`
- Environment: a long random `SECRET_KEY`, `SESSION_COOKIE_SECURE=true`, `PYTHONUNBUFFERED=1`

Keep **one Gunicorn worker**: catalogue caching, per-account locks, and batch
status are held in memory. Each account can have one operation running, with at
most eight active operations across the service. All WFM API traffic is paced
at 2.5 requests per second across accounts. Requests have timeouts; uncertain
mutations are not retried automatically.

The Free service sleeps after 15 idle minutes and can take about a minute to
wake. Restarts clear catalogue caches and batch status. In-flight batches are
not durable: after a restart or an unconfirmed request, inspect your actual WFM
listings before retrying. User passwords are forwarded for sign-in and are not
saved. The WFM token is held in the signed, HTTP-only session cookie.

Render free-plan details: https://render.com/docs/free

## Verification

Build the frontend before running the backend tests:

```bash
npm --prefix frontend ci
npm --prefix frontend run build
npm --prefix frontend run lint
python -m unittest discover -s tests -v
```
