# User-Scan Integration Documentation

## Overview

The PhishGuard application uses **SQLite** to store and manage the relationship between users and their security scans. This document explains how user authentication is integrated with the scan history database.

---

## Database Architecture

### Schema

#### Users Table
```sql
CREATE TABLE users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    google_id   TEXT UNIQUE NOT NULL,
    email       TEXT UNIQUE NOT NULL,
    name        TEXT NOT NULL,
    picture     TEXT DEFAULT '',
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_login  DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_active   INTEGER DEFAULT 1
);
```

#### Scans Table (with User Linking)
```sql
CREATE TABLE scans (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    url        TEXT NOT NULL,
    verdict    TEXT NOT NULL,
    confidence REAL,
    tld        TEXT DEFAULT '',
    timestamp  DATETIME DEFAULT CURRENT_TIMESTAMP,
    results    TEXT,
    user_id    INTEGER REFERENCES users(id)  -- Links scan to user
);
```

#### Indexes for Performance
```sql
CREATE INDEX idx_users_google_id ON users(google_id);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_scans_timestamp ON scans(timestamp);
CREATE INDEX idx_scans_tld ON scans(tld);
CREATE INDEX idx_scans_user_id ON scans(user_id);  -- For fast user scan lookups
```

#### Session Table
```sql
CREATE TABLE login_sessions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id),
    session_token TEXT UNIQUE NOT NULL,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at    DATETIME NOT NULL,
    ip_address    TEXT,
    user_agent    TEXT,
    is_active     INTEGER DEFAULT 1
);
```

---

## User-Scan Connection Flow

### 1. User Registration/Login

**Flow:**
```
Google OAuth → OAuth Callback → Create/Update User → Flask-Login Session
```

**Code Path:**
```python
# auth/routes.py → google_callback()
user = User.create_or_update(google_id, email, name, picture)
login_user(user, remember=True)
```

**Database Operation:**
```python
# database/users.py → upsert_user()
INSERT INTO users (google_id, email, name, picture, created_at, last_login)
VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT(google_id) DO UPDATE SET
    email = excluded.email,
    name = excluded.name,
    picture = excluded.picture,
    last_login = ?
```

### 2. Scan Recording with User Attribution

#### Single URL Scan
**Endpoint:** `POST /api/scan`

**Flow:**
```python
# api/scan.py → api_scan()
user_id = current_user.id if current_user.is_authenticated else None
db.save_scan(url, verdict, confidence, results, user_id=user_id)
```

**Database Operation:**
```python
# database/db.py → save_scan()
INSERT INTO scans (url, verdict, confidence, tld, results, user_id)
VALUES (?, ?, ?, ?, ?, ?)
```

#### Batch CSV Scan
**Endpoint:** `POST /api/batch`

**Flow:**
```python
# api/batch.py → api_batch()
user_id = current_user.id if current_user.is_authenticated else None
db.save_scans_batch(db_rows, user_id=user_id)
```

**Database Operation:**
```python
# database/db.py → save_scans_batch()
INSERT INTO scans (url, verdict, confidence, tld, results, user_id)
VALUES (?, ?, ?, ?, ?, ?)
```

### 3. Retrieving User Scan History

**Endpoint:** `GET /auth/profile` or `GET /auth/history`

**Code Path:**
```python
# auth/routes.py → profile()
scan_count = users_db.get_user_scan_count(current_user.id)
recent = users_db.get_user_scans(current_user.id, limit=5)
```

**Database Query:**
```python
# database/users.py → get_user_scans()
SELECT id, url, verdict, confidence, timestamp FROM scans
WHERE user_id = ? 
ORDER BY timestamp DESC 
LIMIT ?
```

---

## Key Features

### 1. Anonymous and Authenticated Scans
- **Authenticated users:** `user_id` is set to the user's ID
- **Anonymous users:** `user_id` is NULL
- Allows public analytics while tracking authenticated usage

### 2. User Statistics
```python
stats = users_db.get_user_scan_stats(user_id)
# Returns:
{
    "total_scans": 45,
    "phishing_count": 8,
    "safe_count": 37,
    "phishing_percentage": 17.8,
    "scans_last_30_days": 12
}
```

### 3. Connection Verification
```python
is_connected = users_db.verify_user_scan_connection(user_id)
# Returns True if user has associated scans, False otherwise
```

### 4. Foreign Key Integrity
- Scans maintain referential integrity to users
- Soft-delete on account deletion (marks user as inactive)
- Scan records remain in database for analytics

---

## Data Flow Diagram

```
┌─────────────────┐
│  Google OAuth   │
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐
│  Create User Session    │
│  (Flask-Login)          │
└────────┬────────────────┘
         │
    ┌────┴────┐
    │ Scan    │ Batch
    │         │ Scan
    ▼         ▼
┌────────────────────────┐
│  Save Scan with        │
│  user_id (if auth)     │
└────────┬───────────────┘
         │
         ▼
┌────────────────────────┐
│  SQLite Database       │
│  scans table           │
│  (links user_id)       │
└────────┬───────────────┘
         │
    ┌────┴────┬────────┐
    ▼         ▼        ▼
  Profile  History  Stats
  Page     Page     API
```

---

## API Endpoints

### User Profile
- **GET /auth/profile** — View user profile + recent scans (5 most recent)
- **GET /auth/history** — View full scan history (100 most recent)
- **GET /auth/settings** — Account settings and preferences

### Scan Endpoints (Authenticated)
- **POST /api/scan** — Single URL scan (linked to current_user.id if authenticated)
- **POST /api/batch** — Batch CSV scan (linked to current_user.id if authenticated)

### Statistics
- **GET /api/stats** — Overall platform statistics (all users + anonymous)

---

## Database File Location

```
phishing_site_root/
└── webapp/
    └── phishguard.db  ← SQLite database file
```

### WAL Mode
The database uses Write-Ahead Logging (WAL) for improved concurrency:
- Main file: `phishguard.db`
- WAL checkpoint: `phishguard.db-wal`
- Shared memory: `phishguard.db-shm`

---

## Security Considerations

### 1. CSRF Protection
- All state-changing operations (profile update, logout) use CSRF tokens
- Stored in Flask session: `_csrf_token`

### 2. SQLite Injection Prevention
- All queries use parameterized statements (? placeholders)
- User input is never concatenated into SQL strings

### 3. Session Management
- Flask-Login manages session lifecycle
- 30-day inactivity timeout
- HTTPOnly and Secure flags on cookies

### 4. User Privacy
- Soft-delete on account removal (user marked inactive, scans remain for analytics)
- No sensitive data stored (e.g., passwords)
- Profile picture hosted by Google (not stored)

---

## Troubleshooting

### Missing user_id Column
If you have an existing database, the migration in `init_db()` will add the column:
```python
try:
    con.execute("ALTER TABLE scans ADD COLUMN user_id INTEGER REFERENCES users(id)")
except sqlite3.OperationalError:
    pass  # Column already exists
```

### Verifying Connection
Use the verification script:
```bash
cd phishing_site_root/webapp
python scripts/verify_user_scan_integration.py
```

### Checking Database State
```bash
sqlite3 phishguard.db

# Check users
SELECT id, email, created_at FROM users LIMIT 5;

# Check scans with user attribution
SELECT s.id, s.url, s.verdict, u.email, s.timestamp 
FROM scans s 
LEFT JOIN users u ON s.user_id = u.id 
LIMIT 10;

# Count anonymous scans
SELECT COUNT(*) FROM scans WHERE user_id IS NULL;
```

---

## Future Enhancements

1. **Activity Logging** — Track button clicks, page visits per user
2. **Export Functionality** — Allow users to download their scan history
3. **Scan Sharing** — Generate shareable scan reports
4. **Notifications** — Email alerts for detected phishing URLs
5. **API Keys** — Allow programmatic access to scans for authenticated users

---

## References

- **Authentication:** `auth/routes.py`, `auth/models.py`, `auth/oauth_client.py`
- **Database:** `database/db.py`, `database/users.py`
- **API Endpoints:** `api/scan.py`, `api/batch.py`
- **Verification Script:** `scripts/verify_user_scan_integration.py`
