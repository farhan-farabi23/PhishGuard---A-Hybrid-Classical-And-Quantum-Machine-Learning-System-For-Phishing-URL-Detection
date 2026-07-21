# Database Migration Guide: User-Scan Integration

## Overview

This guide explains how the existing PhishGuard database is automatically updated to support the user-scan integration system.

---

## Automatic Migration Process

The application automatically handles database schema migrations when it starts up. **No manual intervention is required.**

### Migration Steps

#### 1. Database Initialization (`init_db()`)

When the Flask app starts, it calls `init_db()` which:

**Step 1:** Creates the `scans` table if it doesn't exist
```python
con.execute("""
    CREATE TABLE IF NOT EXISTS scans (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        url        TEXT    NOT NULL,
        verdict    TEXT    NOT NULL,
        confidence REAL,
        tld        TEXT    DEFAULT '',
        timestamp  DATETIME DEFAULT CURRENT_TIMESTAMP,
        results    TEXT,
        user_id    INTEGER REFERENCES users(id)  -- NEW
    )
""")
```

**Step 2:** Adds the `tld` column if missing (safe on repeated startups)
```python
try:
    con.execute("ALTER TABLE scans ADD COLUMN tld TEXT DEFAULT ''")
except sqlite3.OperationalError:
    pass  # Column already exists — normal on repeated startups
```

**Step 3:** Adds the `user_id` column if missing (safe on repeated startups)
```python
try:
    con.execute("ALTER TABLE scans ADD COLUMN user_id INTEGER REFERENCES users(id)")
except sqlite3.OperationalError:
    pass  # Column already exists — normal on repeated startups
```

**Step 4:** Creates performance indexes
```python
con.execute("CREATE INDEX IF NOT EXISTS idx_scans_timestamp ON scans(timestamp)")
con.execute("CREATE INDEX IF NOT EXISTS idx_scans_tld ON scans(tld)")
con.execute("CREATE INDEX IF NOT EXISTS idx_scans_user_id ON scans(user_id)")  -- NEW
```

#### 2. User Tables Initialization (`init_user_tables()`)

The app then calls `init_user_tables()` which:

**Creates the `users` table:**
```python
con.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        google_id   TEXT     UNIQUE NOT NULL,
        email       TEXT     UNIQUE NOT NULL,
        name        TEXT     NOT NULL,
        picture     TEXT     DEFAULT '',
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
        last_login  DATETIME DEFAULT CURRENT_TIMESTAMP,
        is_active   INTEGER  DEFAULT 1
    )
""")
```

**Creates the `login_sessions` table:**
```python
con.execute("""
    CREATE TABLE IF NOT EXISTS login_sessions (
        id            INTEGER  PRIMARY KEY AUTOINCREMENT,
        user_id       INTEGER  NOT NULL REFERENCES users(id),
        session_token TEXT     UNIQUE NOT NULL,
        created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
        expires_at    DATETIME NOT NULL,
        ip_address    TEXT,
        user_agent    TEXT,
        is_active     INTEGER  DEFAULT 1
    )
""")
```

**Adds the `user_id` foreign key to scans table (if missing):**
```python
try:
    con.execute("ALTER TABLE scans ADD COLUMN user_id INTEGER REFERENCES users(id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_scans_user_id ON scans(user_id)")
except sqlite3.OperationalError:
    pass  # Column already exists — normal on repeated startups
```

---

## Migration Scenarios

### Scenario 1: New Installation
- ✅ All tables created with `user_id` column from the start
- ✅ All indexes created
- ✅ Ready to use immediately

### Scenario 2: Existing Database (Old Version)
- ✅ `scans` table exists without `user_id` column
- ✅ ALTER TABLE adds `user_id` column with NULL defaults
- ✅ Existing scans have `user_id = NULL` (marked as anonymous)
- ✅ New scans (from authenticated users) get `user_id` set correctly
- ✅ User profile pages work for authenticated users going forward

### Scenario 3: Partial Migration
- ✅ If migration was interrupted, running the app again will:
  - Detect existing `user_id` column
  - Skip the ALTER TABLE (no error)
  - Continue normally

---

## Data Consistency

### Existing Scans (After Migration)

All existing scans from before the migration will have:
- `user_id = NULL` (anonymous)
- All other fields unchanged
- Preserved in database for analytics

### Example Query to Check Status
```sql
-- Count anonymous scans
SELECT COUNT(*) as anonymous_scans 
FROM scans 
WHERE user_id IS NULL;

-- Count authenticated scans
SELECT COUNT(*) as user_scans 
FROM scans 
WHERE user_id IS NOT NULL;

-- View scans with user info
SELECT 
    s.id, 
    s.url, 
    s.verdict, 
    u.email as user_email,
    s.timestamp
FROM scans s
LEFT JOIN users u ON s.user_id = u.id
ORDER BY s.timestamp DESC
LIMIT 20;
```

---

## Verification

### Automatic Verification
Run the verification script to ensure migration was successful:

```bash
cd phishing_site_root/webapp
python scripts/verify_user_scan_integration.py
```

**Expected Output:**
```
[1] Checking database schema...
  ✅ PASSED: All required columns exist
  ✅ PASSED: All indexes present

[2] Testing user creation and scan linking...
  ✅ User created: ID=1, Email=test@example.com
  ✅ Scan saved for user_id=1
  ✅ Scan correctly linked to user

[3] Testing batch scan linking...
  ✅ Batch scans saved for user_id=1

[4] Testing user statistics...
  ✅ User 1 statistics:
     - Total scans: 3
     - Phishing: 0
     - Safe: 3
     - Phishing rate: 0.0%
     - Last 30 days: 3

✅ All tests passed! User-scan integration is working correctly.
```

### Manual Verification via SQLite
```bash
sqlite3 phishguard.db

# Check schema
.schema scans

# Expected output should include:
# user_id INTEGER REFERENCES users(id)

# Check data integrity
PRAGMA foreign_keys = ON;
SELECT COUNT(*) FROM scans WHERE user_id NOT NULL AND user_id NOT IN (SELECT id FROM users);
# Should return 0 (no orphaned references)
```

---

## Rollback (If Needed)

If you need to rollback to the old schema:

```sql
-- WARNING: Only do this if you know what you're doing!

-- Option 1: Drop the column (loses user attribution)
ALTER TABLE scans DROP COLUMN user_id;

-- Option 2: Create a backup before migration
-- Recommended approach:
-- 1. Stop the app
-- 2. Copy phishguard.db to phishguard.db.backup
-- 3. Start the app (runs migration)
-- 4. If needed, restore from backup
```

---

## Performance Impact

### Index Addition
Adding `idx_scans_user_id` index has minimal impact:
- Initial creation: ~50ms for 10,000 scans
- Subsequent queries: 10-100x faster for user-specific lookups
- Disk overhead: ~1-5% depending on database size

### Column Addition
Adding `user_id` column:
- Initial migration: ~100ms for 10,000 scans
- No ongoing performance impact
- Disk overhead: ~4 bytes per scan

---

## Troubleshooting

### Issue: "database table is locked" error

**Cause:** Multiple processes accessing database simultaneously

**Solution:**
```python
# db.py already uses WAL mode which handles this:
con.execute("PRAGMA journal_mode=WAL")
con.execute("PRAGMA synchronous=NORMAL")
```

### Issue: "no such column: user_id" error

**Cause:** Migration didn't run completely

**Solution:**
```bash
# Restart the Flask app (it will re-run migrations)
python app.py
```

### Issue: Foreign key constraint violations

**Cause:** user_id references a deleted user

**Solution:**
```sql
-- Enable foreign key checks
PRAGMA foreign_keys = ON;

-- Find orphaned scans
SELECT COUNT(*) FROM scans 
WHERE user_id NOT NULL AND user_id NOT IN (SELECT id FROM users);

-- Fix by setting orphaned scans to NULL
UPDATE scans SET user_id = NULL 
WHERE user_id NOT IN (SELECT id FROM users);
```

---

## Before and After

### Before Migration
```sql
sqlite> .schema scans
CREATE TABLE scans(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  url TEXT NOT NULL,
  verdict TEXT NOT NULL,
  confidence REAL,
  tld TEXT DEFAULT '',
  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
  results TEXT
);
```

### After Migration
```sql
sqlite> .schema scans
CREATE TABLE scans(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  url TEXT NOT NULL,
  verdict TEXT NOT NULL,
  confidence REAL,
  tld TEXT DEFAULT '',
  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
  results TEXT,
  user_id INTEGER REFERENCES users(id)
);

CREATE INDEX idx_scans_user_id ON scans(user_id);
```

---

## Next Steps

1. **Start the app** — Automatic migration runs on startup
2. **Run verification** — Confirm integration is working
3. **Test user flow** — Sign up, scan URLs, check profile
4. **Monitor logs** — Watch for any migration errors in console output

For detailed documentation, see [USER_SCAN_INTEGRATION.md](./USER_SCAN_INTEGRATION.md)
