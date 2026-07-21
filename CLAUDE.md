# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Start

### 1. Install Dependencies
```bash
cd phishing_site_root
pip install -r requirements.txt
```

### 2. Preprocess Dataset (One-Time)
Before running the app, generate the training data by executing:
```
phishing_site_root/preprocessing-dataset/data_preprocessing.ipynb
```
This produces `processed_data.csv`, which is loaded by the Flask app at startup.

### 3. Environment Setup
Copy `.env.example` to `.env` and configure:
```bash
cd phishing_site_root/webapp
cp .env.example .env
```

Edit `.env` to set:
- `SECRET_KEY`: Generate with `python -c "import secrets; print(secrets.token_hex(32))"`
- `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`: For OAuth (optional; simple email/password auth works without it)
- `FLASK_ENV`: Set to `production` for HTTPS-only cookies (optional, defaults to development)

### 4. Run the Web App
```bash
cd phishing_site_root/webapp
python app.py
```
Starts on http://127.0.0.1:5000. The app initializes the database and trains all 9 models in memory during startup (~2-3 minutes).

**First Use:** Create an account at http://127.0.0.1:5000/auth/register with any email/password (no OAuth required)

### 5. Run Tests
```bash
cd phishing_site_root/webapp
python test_auth.py                     # Test auth system
```
Test data: `phishing_site_root/testing/test_urls_100.csv`

## Architecture

### Application Flow

**Entry point**: `phishing_site_root/webapp/app.py`

1. **Initialization** (on app startup):
   - Database initialized (`phishguard.db`)
   - Model loader triggers: loads dataset, trains classical/quantum models (~2-3 min)
   - Flask-Login + CSRF protection configured

2. **User routes**:
   - **Public**: `/` (landing page — accessible to all)
   - **Protected** (require login): `/analyser`, `/batch`, `/dashboard`, `/visualizer`
   - **Auth**: `/auth/login`, `/auth/register`, `/auth/logout`

3. **API endpoints**:
   - **Public**: `/api/health`, `/api/auth-status`
   - **Protected**: `/api/scan`, `/api/batch`, `/api/circuit`, `/api/stats`, `/api/history`, `/api/clear-history` (all require login)

### Startup and Model Loading
- **Entry point**: `phishing_site_root/webapp/app.py`
- **Model initialization**: `models/loader.py` runs at startup:
  1. Loads `processed_data.csv` (must exist; created by preprocessing notebook)
  2. Samples 5000 URLs for training
  3. Builds and trains **2 preprocessing pipelines**:
     - **Classical**: TF-IDF → SVD (200 components) → StandardScaler
     - **Quantum**: TF-IDF → SVD (50 components) → StandardScaler → PCA (4 components) → MinMaxScaler [0, π]
  4. Trains 6 classical models: KNN, Logistic Regression, Naive Bayes, SVM/LinearSVC, Random Forest, MLP
  5. Loads 3 quantum models: VQC (pre-trained weights), QKNN, QSVM (pre-computed kernel matrix)

### Prediction Pipeline
- **Function**: `loader.predict_all(url)` in `models/loader.py`
- **Flow**:
  1. Extract URL features (TF-IDF bag of words)
  2. Route through two branches:
     - **Classical branch**: Standard scaling → KNN, LogReg, NB, SVM, RF, MLP predictions
     - **Quantum branch**: PCA + angle encoding → VQC, QKNN, QSVM predictions
  3. Ensemble: Majority vote across all 9 models
  4. Returns: verdict ("good"/"bad"), confidence score, per-model votes

### Quantum Circuits
- **Location**: `models/quantum.py`
- **Device**: Single PennyLane `default.qubit` device protected by `_dev_lock` (threading lock)
- **Models**:
  - **VQC** (Variational Quantum Classifier): AngleEmbedding + parameterized RY/RZ layers + CNOT ring, trained weights loaded from `model_VQC/result/vqc_weights.npy`
  - **QKNN**: Fidelity circuit (adjoint swap test)
  - **QSVM**: IQP feature map (Hadamard + RZ + ZZ interactions per Havlíček et al.)

### API Surface
All endpoints return JSON. Defined in `api/` directory:

**Public endpoints (no login required):**
- `GET /api/health` — Readiness probe (returns `{"status": "ok", "initialized": true/false}`)
- `GET /api/auth-status` — Current auth state (returns `{"authenticated": bool, "email": str|null}`)

**Protected endpoints (login required):**
- `POST /api/scan` — Scan single URL (body: `{"url": "...", "include_quantum": true/false}`), returns per-model + ensemble results + scan ID
- `POST /api/batch` — Upload CSV file, scan up to 1000 URLs (classical models only for speed)
- `GET /api/circuit` — Fetch 4 quantum angle-encoding parameters for a URL (for 3D visualizer)
- `GET /api/stats` — Dashboard analytics (scan counts, model accuracy, etc.)
- `GET /api/history` — Recent scan records from SQLite (paginated)
- `GET /api/clear-history` — Delete all user's scan history

### Authentication & Storage
- **Auth method**: Simple email/password (anyone can register) via `auth/routes.py`
- **Password security**: Hashed with werkzeug.security
- **Session management**: Flask-Login with 30-day remember-me cookies
- **CSRF protection**: Session-based tokens for form POSTs; JSON APIs exempt
- **Security headers**: X-Frame-Options, X-Content-Type-Options, CSP configured
- **CORS**: Restricts to localhost + browser extension origins (no wildcard)
- **Database**: SQLite at `webapp/phishguard.db`
  - User table: id, email, password_hash, name, created_at, last_login, is_active
  - Scan history: id, user_id, url, verdict, confidence, timestamp
- **Environment variables**:
  - `SECRET_KEY`: Session encryption key (required for production)
  - `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`: OAuth credentials (optional; OAuth currently disabled)
  - `FLASK_ENV`: Set to `production` for HTTPS-only cookies
  - `PHISHGUARD_DB_PATH`: Custom database path (optional; defaults to `webapp/phishguard.db`)

### Landing Page
- **Route**: `GET /` (public, no login required)
- **Template**: `templates/landing.html`
- **Features**:
  - Hash-based navigation: `#about`, `#services`, `#features` (no page reload)
  - Responsive design with navbar and footer
  - **Authenticated users**: See user name, quick links to Analyser/Batch/Dashboard
  - **Unauthenticated users**: See Sign In/Register CTAs
  - Footer links to core features (conditional based on auth status)

### 3D Quantum Circuit Visualizer
- **Route**: `GET /visualizer` (protected, login required)
- **Template**: `templates/visualizer.html`
- **Backend**: `GET /api/circuit` returns 4 angle values (0 to π) for 4 qubits
- **Frontend**: `static/js/3d-visualizer.js` renders interactive 3D scene using Three.js:
  - 4 qubits as color-coded spheres (angle → hue via HSL color space)
  - 12 CNOT gates as connecting lines (3 layers of entanglement)
  - OrbitControls: mouse drag to rotate, scroll to zoom
  - Educational info panel explains each component
  - Graceful fallback if WebGL unavailable
- **Performance**: Scene renders in <100ms, 60 FPS on modern browsers
- **Browser support**: Chrome 90+, Firefox 88+, Safari 14+, Edge 90+

### Browser Extension
- **Manifest**: `browser_extension/manifest.json` (Manifest V3)
- **Target**: Chrome and Firefox 109+
- **Hardcoded server**: Connects only to http://localhost:5000 (no configuration)
- **Entry points**:
  - `popup.html/js/css` — Quick scan UI (popup icon)
  - `warning.html/js` — Full-page warning if phishing detected
  - `background.js`, `content.js` — Message routing

## Common Development Tasks

### Add a New Scan Feature
1. Add endpoint to `api/scan.py` with `@login_required` decorator
2. Call `loader.predict_all(url, include_quantum)` for predictions
3. Store result in database via `database/queries.py`
4. Add frontend code in `templates/index.html` and `static/js/analyser.js`

### Add a New API Endpoint
1. Create blueprint in `api/` directory
2. Add `@login_required` if it's a protected endpoint
3. Register blueprint in `app.py` line 81-84
4. Add CSRF/CORS handling if needed (already configured globally)

### Debugging Model Predictions
1. Check `models/loader.is_initialized()` returns `True` via `/api/health`
2. Test `loader.predict_all(url, include_quantum=False)` in Python shell
3. Check `processed_data.csv` exists (created by preprocessing notebook)
4. Verify quantum circuit weights loaded in `models/quantum.py`

### Testing a Route Change
1. Test locally: start app, navigate to changed URL
2. Check browser console for JS errors
3. Check server logs for Python errors
4. Run `test_auth.py` to verify auth system still works

## Key Implementation Details

### Threading & Concurrency
- Quantum device (`default.qubit`) is shared across threads. Protected by `_dev_lock` in `models/quantum.py` — prevents circuit state corruption under concurrent requests.
- Flask runs with `threaded=True` in `app.py` (line 244) to handle multiple users simultaneously.

### Feature Extraction & Encoding
- URLs tokenized into character n-grams → TF-IDF vectorization → dimensionality reduction via SVD
- **Classical features**: 200-D (post-SVD) → StandardScaler → 6 classical models
- **Quantum features**: 50-D (post-SVD) → StandardScaler → PCA (4-D) → MinMaxScaler [0, π] angle encoding → 3 quantum models
- Angle encoding: Maps 4-D vector to [0, π] range for quantum state preparation

### Model Ensemble
- 9 models vote: 6 classical + 3 quantum
- Majority vote determines final verdict ("good"/"bad")
- Confidence = count of matching votes / 9
- Per-model predictions returned for transparency

### Database Design
- SQLite (no complex setup required)
- User table: Simple auth (id, email, password_hash, name, created_at, last_login, is_active)
- Scan table: Linked to user_id for history & analytics
- Schema auto-initialized on app startup (`database/db.py`)

### Production vs Development
- **HTTPS-only cookies**: Enabled when `FLASK_ENV=production`
- **CSRF tokens**: Enforced on all form POSTs; JSON APIs exempt
- **Default SECRET_KEY**: Changed in production (generate with `secrets.token_hex(32)`)
- **CORS**: Restricted to localhost + browser extension origins (no wildcard)

## Security Checklist

**When adding new routes or endpoints:**
- ✅ Add `@login_required` decorator if the endpoint accesses user data or models
- ✅ Validate URL length & format in API endpoints (see `api/helpers.py`)
- ✅ Use `request.get_json(silent=True)` to safely parse JSON
- ✅ Never trust user input for SQL or shell commands (use ORM/parameterized queries)
- ✅ Include CSRF token in all HTML forms that POST (auto-injected by Jinja2)
- ✅ Ensure password hashing uses `werkzeug.security.generate_password_hash()`

**When modifying templates:**
- ✅ Use Jinja2 `{{ variable }}` (auto-escaped) not raw HTML
- ✅ Use `{{ current_user.email }}` to access authenticated user data
- ✅ Include `{{ csrf_token() }}` in POST forms

**When deploying to production:**
- ✅ Set `FLASK_ENV=production`
- ✅ Generate and set a new `SECRET_KEY`
- ✅ Use a production WSGI server (e.g., gunicorn), not Flask's built-in server
- ✅ Set up HTTPS with valid SSL certificates
- ✅ Verify `.env` file is in `.gitignore` (never commit secrets)

## Gotchas to Avoid

- **Quantum device lock**: Always acquire `_dev_lock` in `quantum.py` when calling quantum circuits (threading issue)
- **Preprocessing required**: App crashes at startup if `processed_data.csv` is missing — run preprocessing notebook first
- **Model timeout**: Training 9 models takes 2-3 minutes at startup (not suitable for serverless/lambda)
- **CSV upload size**: Maximum 5 MB file size enforced (see `app.config["MAX_CONTENT_LENGTH"]`)
- **OAuth disabled**: Google OAuth environment variables in `.env` are unused (simple email/password only)
- **SQLite limitations**: Not suitable for high concurrency (consider PostgreSQL for scaling)

## Testing

- **Quick test**: `webapp/test_auth.py` — Tests user registration, password hashing, session management
  ```bash
  cd phishing_site_root/webapp
  python test_auth.py
  ```
- **Test data**: `testing/test_urls_100.csv` — 100 sample URLs for manual batch testing
- **Manual verification**: Start the app and test workflows (landing page, login, scan, batch, visualizer)

## Key Files

| File | Purpose |
|------|---------|
| `webapp/app.py` | Flask entry point; route registration, CSRF/CORS/security config |
| `webapp/api/scan.py` | `/api/scan`, `/api/stats`, `/api/health`, `/api/auth-status` endpoints |
| `webapp/api/batch.py` | `/api/batch` — CSV upload & scanning |
| `webapp/api/circuit.py` | `/api/circuit` — Angle encoding for 3D visualizer |
| `webapp/auth/routes.py` | Login, register, logout endpoints |
| `webapp/auth/models.py` | Flask-Login User model, database interaction |
| `webapp/models/loader.py` | Model initialization, `predict_all(url)` prediction pipeline |
| `webapp/models/quantum.py` | Quantum circuits (VQC, QKNN, QSVM) with PennyLane |
| `webapp/database/db.py` | SQLite connection, schema initialization |
| `webapp/database/users.py` | User CRUD + password hashing |
| `webapp/static/js/3d-visualizer.js` | Three.js 3D quantum circuit rendering |
| `webapp/templates/landing.html` | Public landing page (for all users) |
| `webapp/templates/index.html` | Analyser page (scan single URLs) |
| `webapp/templates/batch.html` | Batch scanner (CSV upload) |
| `webapp/templates/visualizer.html` | 3D quantum visualizer |
| `webapp/templates/dashboard.html` | Scan history & statistics |

## Project Structure

```
phishing_site_root/
├── requirements.txt                    # Python dependencies
├── preprocessing-dataset/
│   ├── data_preprocessing.ipynb        # Generate processed_data.csv (MUST RUN FIRST)
│   └── processed_data.csv              # Training dataset (output)
├── models/
│   ├── preprocessing/                  # Preprocessing pipeline notebooks
│   ├── classical/                      # Classical ML model training notebooks
│   └── quantum/                        # Quantum ML model training notebooks
├── testing/
│   └── test_urls_100.csv               # Sample URLs for testing
├── thesis_documents/                   # Project documentation, screenshots
├── browser_extension/                  # Chrome/Firefox extension
└── webapp/
    ├── app.py                          # Flask entry point
    ├── .env.example                    # Environment variables template
    ├── test_auth.py                    # Auth system test
    ├── api/                            # API blueprints (scan, batch, circuit)
    ├── auth/                           # Authentication (routes, models)
    ├── models/                         # ML pipelines (loader.py, quantum.py)
    ├── database/                       # DB schema & access (db.py, users.py, queries.py)
    ├── routes/                         # Additional page routes (if any)
    ├── scripts/                        # Utility scripts
    ├── docs/                           # Documentation (integration guides, etc)
    ├── templates/                      # Jinja2 HTML (landing, index, batch, visualizer, dashboard)
    ├── static/
    │   ├── js/                         # JavaScript (analyser.js, batch.js, dashboard.js, visualizer.js, 3d-visualizer.js)
    │   └── css/                        # Stylesheets
    └── phishguard.db                   # SQLite database (created at runtime)
```
